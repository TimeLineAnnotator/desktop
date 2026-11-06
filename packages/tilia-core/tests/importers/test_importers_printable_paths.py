"""An importer's failure message can always be printed: a file name that isn't
valid UTF-8 reaches Python on Linux with a lone surrogate, which can't be
encoded, so the messages write it as its escape. Other text stays as it is.

The files are real where the system lets us name one (Linux, and Windows on
NTFS); a test is skipped where it doesn't."""

import pytest
from import_docs import document, timeline

from tilia_core import importers
from tilia_core.importers import ImportFailed, hierarchy, marker, metadata, pdf
from tilia_core.importers import range as range_

BAD = "bad\udcff.csv"
ESCAPED = "bad\\udcff.csv"  # the name as written out: a backslash, "udcff"
ACCENTED = "música-é.csv"
NOT_UTF8 = b"time,page_number\n\xff\xfe\xfa,1\n"


def failure(call, *args, **kwargs):
    with pytest.raises(ImportFailed) as raised:
        call(*args, **kwargs)
    return raised.value


def named(tmp_path, name, content):
    """The file `name` in `tmp_path`, or a skip where the system can't name it."""
    path = tmp_path / name
    try:
        path.write_bytes(content)
    except OSError:
        pytest.skip("this system can't name a file that isn't UTF-8")
    return path


def printable_text(error):
    text = str(error)
    assert text.encode("utf-8")
    assert error.message.encode("utf-8")
    return text


def by_time(module, kind, **document_kwargs):
    target = timeline(kind)
    doc = document(timelines=[target], **document_kwargs)
    return lambda path: failure(module.import_by_time, doc, target.id, path)


IMPORTERS = [
    pytest.param((marker, "marker"), id="marker"),
    pytest.param((hierarchy, "hierarchy"), id="hierarchy"),
    pytest.param((range_, "range"), id="range"),
    pytest.param((pdf, "pdf"), id="pdf"),
]


@pytest.mark.parametrize("importer", IMPORTERS)
def test_a_csv_that_isnt_utf8_names_its_file_as_an_escape(tmp_path, importer):
    path = named(tmp_path, BAD, NOT_UTF8)

    text = printable_text(by_time(*importer)(path))

    assert ESCAPED in text
    assert "is not a valid UTF-8 encoded CSV file" in text


@pytest.mark.parametrize("importer", IMPORTERS)
def test_an_empty_csv_names_its_file_as_an_escape(tmp_path, importer):
    path = named(tmp_path, BAD, b"")

    text = printable_text(by_time(*importer)(path))

    assert text.startswith(f"{ESCAPED}: ")


@pytest.mark.parametrize("importer", IMPORTERS)
def test_a_failure_before_the_file_is_read_names_the_file_as_an_escape(importer):
    # No media length: the import fails before it reads the file.
    text = printable_text(by_time(*importer, media_length=None)(BAD))

    assert text.startswith(f"{ESCAPED}: ")


@pytest.mark.parametrize("importer", IMPORTERS)
def test_a_name_with_accents_is_unchanged(tmp_path, importer):
    path = named(tmp_path, ACCENTED, NOT_UTF8)

    text = printable_text(by_time(*importer)(path))

    assert text == f"'{path}' is not a valid UTF-8 encoded CSV file."
    assert ACCENTED in text


def test_import_csv_writes_the_escape(tmp_path):
    path = named(tmp_path, BAD, NOT_UTF8)
    target = timeline("marker")
    doc = document(timelines=[target])

    error = failure(importers.import_csv, doc, target.id, path, by="time")

    assert ESCAPED in printable_text(error)


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(b'{"a": "\xff"}', id="not utf-8"),
        pytest.param(b"{nope", id="not json"),
        pytest.param(b"[1]", id="not an object"),
        pytest.param(b"[" * 100_000, id="too deep"),
    ],
)
def test_the_metadata_importers_messages_write_the_escape(tmp_path, content):
    path = named(tmp_path, "bad\udcff.json", content)

    error = failure(metadata.import_metadata, document(), path)

    assert "bad\\udcff.json" in printable_text(error)


def test_the_metadata_importers_message_for_a_missing_file(tmp_path):
    # Real: the file isn't there, so `open` itself raises.
    error = failure(metadata.import_metadata, document(), tmp_path / "bad\udcff.json")

    assert "bad\\udcff.json" in printable_text(error)


def test_the_message_names_the_file_once(tmp_path, monkeypatch):
    # The message names the file already, so the failure doesn't add its name.
    monkeypatch.chdir(tmp_path)

    error = failure(metadata.import_metadata, document(), "bad\udcff.json")

    assert str(error) == "File bad\\udcff.json not found."


def test_a_recursion_error_in_a_field_names_the_file_as_an_escape(
    tmp_path, monkeypatch
):
    path = named(tmp_path, "bad\udcff.json", b'{"a": "b"}')

    def too_deep(value):
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(metadata, "_field", too_deep)

    error = failure(metadata.import_metadata, document(), path)

    assert "bad\\udcff.json" in printable_text(error)


def test_the_metadata_importers_message_keeps_accents(tmp_path):
    path = tmp_path / "música-é.json"

    error = failure(metadata.import_metadata, document(), path)

    assert str(error) == f"File {path} not found."
