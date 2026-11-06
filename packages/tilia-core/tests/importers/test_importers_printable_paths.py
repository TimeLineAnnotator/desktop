"""An importer's failure message can always be printed: a file name that isn't
valid UTF-8 reaches Python on Linux with a lone surrogate, which can't be
encoded, so the messages write it as its escape. Other text stays as it is."""

import io

import pytest
from import_docs import document, timeline

from tilia_core import importers
from tilia_core.importers import ImportFailed, hierarchy, marker, pdf
from tilia_core.importers import range as range_

BAD = "bad\udcff.csv"
ESCAPED = "bad\\udcff.csv"
ACCENTED = "música-é.csv"


def failure(call, *args):
    with pytest.raises(ImportFailed) as raised:
        call(*args)
    return raised.value


def by_time(module, kind):
    target = timeline(kind)
    doc = document(media_length=None, timelines=[target])
    return lambda path: failure(module.import_by_time, doc, target.id, path)


IMPORTERS = [
    pytest.param(by_time(marker, "marker"), id="marker"),
    pytest.param(by_time(hierarchy, "hierarchy"), id="hierarchy"),
    pytest.param(by_time(range_, "range"), id="range"),
    pytest.param(by_time(pdf, "pdf"), id="pdf"),
]


@pytest.mark.parametrize("run", IMPORTERS)
def test_a_name_that_is_not_utf8_is_written_as_its_escape(run):
    text = str(run(BAD))

    assert text.encode("utf-8")
    assert ESCAPED in text


@pytest.mark.parametrize("run", IMPORTERS)
def test_a_name_with_accents_is_unchanged(run):
    assert str(run(ACCENTED)).startswith(f"{ACCENTED}: ")


def test_import_csv_writes_the_escape():
    target = timeline("marker")
    doc = document(media_length=None, timelines=[target])

    error = failure(lambda: importers.import_csv(doc, target.id, BAD, by="time"))

    assert ESCAPED in str(error)
    assert str(error).encode("utf-8")


class FakeFile(io.StringIO):
    """What `open` gives, in place of a file that can't be created here."""


def opening(monkeypatch, module, text=None, raises=None):
    def fake_open(path, *args, **kwargs):
        if raises is not None:
            raise raises
        return FakeFile(text)

    monkeypatch.setattr(module, "open", fake_open, raising=False)


def decode_error():
    return UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")


def test_a_csv_that_is_not_utf8_names_the_file_as_an_escape(monkeypatch):
    from tilia_core.importers import _csv

    class Broken(io.StringIO):
        def __next__(self):
            raise decode_error()

    monkeypatch.setattr(_csv, "open", lambda *a, **k: Broken(), raising=False)

    error = failure(_csv.read_csv, BAD)

    assert ESCAPED in str(error)
    assert str(error).encode("utf-8")


@pytest.mark.parametrize(
    "kind",
    ["missing", "not utf-8", "not json", "not an object", "too deep"],
)
def test_the_metadata_importers_messages_write_the_escape(monkeypatch, kind):
    from tilia_core.importers import metadata

    if kind == "missing":
        opening(monkeypatch, metadata, raises=FileNotFoundError())
    elif kind == "not utf-8":
        opening(monkeypatch, metadata, raises=decode_error())
    else:
        text = {
            "not json": "{nope",
            "not an object": "[1]",
            "too deep": "[" * 100_000,
        }[kind]
        opening(monkeypatch, metadata, text=text)
    doc = document()

    error = failure(metadata.import_metadata, doc, BAD)

    assert str(error).encode("utf-8")
    assert error.message.encode("utf-8")
    assert ESCAPED in str(error)


def test_the_metadata_importers_message_keeps_accents(monkeypatch):
    from tilia_core.importers import metadata

    opening(monkeypatch, metadata, raises=FileNotFoundError())

    error = failure(metadata.import_metadata, document(), ACCENTED)

    assert str(error) == f"File {ACCENTED} not found."
