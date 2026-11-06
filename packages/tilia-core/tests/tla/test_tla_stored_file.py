"""The file a stored path names (TimeLineAnnotator/project-management#415): one
public lookup for a PDF timeline's path and the media's, with the same rules: a
relative path from the file's folder, its decomposed name tried when the stored
one isn't found, a path that starts with `//` a server path, and a backslash as
the system reads it (FR-021, FR-033)."""

import json
import os
import unicodedata
from pathlib import Path
from types import SimpleNamespace

import pytest

from tilia_core import tla
from tilia_core.tla import media_files

WINDOWS = os.name == "nt"
posix_only = pytest.mark.skipif(WINDOWS, reason="a name with a backslash, on POSIX")
windows_only = pytest.mark.skipif(not WINDOWS, reason="a separator only on Windows")
NFC = unicodedata.normalize("NFC", "Ständchen")
NFD = unicodedata.normalize("NFD", "Ständchen")
SERVER_PATH = "//server-415/share/scores/piece.pdf"


def a_file(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF")
    return path


def with_pdf_timeline(piece, stored):
    """The document of a file at `piece`, read back, with a PDF timeline whose
    path is `stored`; and its path as the document holds it."""
    piece.parent.mkdir(parents=True, exist_ok=True)
    timeline_id = tla.new_id()
    content = json.loads(tla.canonical_bytes(tla.new_document()))
    content["timelines"][timeline_id] = {
        "kind": "Pdf",
        "name": "Score",
        "ordinal": 1,
        "height": 30,
        "path": stored,
        "components": {},
    }
    piece.write_text(json.dumps(content), "utf-8")
    doc = tla.read(piece)
    return doc, doc.timelines[timeline_id].attrs["path"]


@pytest.fixture
def servers(monkeypatch):
    """Lookups of a Windows server path, which Windows would make on the network:
    each is recorded, with "/", and finds a file only where `there` says."""
    looked_up = []
    there = set()
    real = os.path.isfile

    def isfile(path):
        text = os.fspath(path).replace("\\", "/")
        if not text.startswith("//"):
            return real(path)
        looked_up.append(text)
        return text in there

    monkeypatch.setattr(os.path, "isfile", isfile)
    return SimpleNamespace(looked_up=looked_up, there=there)


# A PDF timeline's path


def test_a_relative_path_is_found_from_the_files_folder(tmp_path):
    pdf = a_file(tmp_path / "scores" / "piece.pdf")
    piece = tmp_path / "corpus" / "piece.tla"
    _, stored = with_pdf_timeline(piece, "../scores/piece.pdf")
    assert os.path.samefile(tla.stored_file(piece, stored), pdf)


def test_it_doesnt_depend_on_the_working_folder(tmp_path, monkeypatch):
    pdf = a_file(tmp_path / "corpus" / "scores" / "piece.pdf")
    monkeypatch.chdir(tmp_path)
    piece = Path("corpus") / "piece.tla"
    found = tla.stored_file(piece, "scores/piece.pdf")
    assert os.path.samefile(found, pdf)
    assert found.is_absolute()


def test_a_str_gives_the_same_as_a_path(tmp_path):
    pdf = a_file(tmp_path / "piece.pdf")
    piece = tmp_path / "piece.tla"
    assert os.path.samefile(tla.stored_file(str(piece), "piece.pdf"), pdf)


def test_the_decomposed_name_is_tried_when_the_stored_one_isnt_found(tmp_path):
    # The name as macOS's older file system gave it, copied elsewhere. In NFC in
    # the file, as every text is but a score's.
    pdf = a_file(tmp_path / f"{NFD}.pdf")
    piece = tmp_path / "piece.tla"
    _, stored = with_pdf_timeline(piece, f"{NFD}.pdf")
    assert stored == f"{NFC}.pdf"
    assert os.path.samefile(tla.stored_file(piece, stored), pdf)


def test_a_decomposed_folder_is_found_too(tmp_path):
    pdf = a_file(tmp_path / NFD / "piece.pdf")
    piece = tmp_path / "piece.tla"
    found = tla.stored_file(piece, f"{NFC}/piece.pdf")
    assert os.path.samefile(found, pdf)


def test_a_path_with_two_slashes_is_a_server_path(tmp_path, servers):
    piece = tmp_path / "piece.tla"
    _, stored = with_pdf_timeline(piece, SERVER_PATH)
    servers.there.add(SERVER_PATH)
    found = tla.stored_file(piece, stored)
    if WINDOWS:
        assert found == Path(SERVER_PATH)
        assert servers.looked_up == [SERVER_PATH]
    else:  # another system's path, never looked up here
        assert (found, servers.looked_up) == (None, [])


def test_a_server_path_with_no_file_there_is_none(tmp_path, servers):
    assert tla.stored_file(tmp_path / "piece.tla", SERVER_PATH) is None


@windows_only
def test_a_backslash_separates_folders_on_windows(tmp_path):
    pdf = a_file(tmp_path / "scores" / "piece.pdf")
    piece = tmp_path / "piece.tla"
    _, stored = with_pdf_timeline(piece, "scores\\piece.pdf")
    assert stored == "scores\\piece.pdf"
    assert os.path.samefile(tla.stored_file(piece, stored), pdf)


@posix_only
def test_a_backslash_is_part_of_a_name_on_macos_and_linux(tmp_path):
    a_file(tmp_path / "scores" / "piece.pdf")
    piece = tmp_path / "piece.tla"
    _, stored = with_pdf_timeline(piece, "scores\\piece.pdf")
    assert tla.stored_file(piece, stored) is None
    named = a_file(tmp_path / "scores\\piece.pdf")
    assert os.path.samefile(tla.stored_file(piece, stored), named)


def test_an_absolute_path_is_taken_as_it_is(tmp_path):
    pdf = a_file(tmp_path / "scores" / "piece.pdf")
    piece = tmp_path / "corpus" / "piece.tla"
    assert os.path.samefile(tla.stored_file(piece, str(pdf)), pdf)


def test_an_old_files_pdf_is_found_once_migrated(tmp_path):
    pdf = a_file(tmp_path / "scores" / "piece.pdf")
    piece = tmp_path / "corpus" / "piece.tla"
    piece.parent.mkdir()
    timeline = {
        "kind": "Pdf",
        "name": "Score",
        "ordinal": 1,
        "height": 30,
        "is_visible": True,
        "path": str(pdf),
        "components": {},
    }
    content = {
        "app_name": "TiLiA",
        "version": "0.7.0",
        "file_path": str(piece),
        "media_path": "",
        "media_metadata": {"media length": 60},
        "timelines": {"1": timeline},
    }
    piece.write_text(json.dumps(content), "utf-8")
    doc = tla.read(piece)
    (read,) = doc.timelines.values()
    assert read.attrs["path"] == "../scores/piece.pdf"
    assert os.path.samefile(tla.stored_file(piece, read.attrs["path"]), pdf)


# What it finds nothing for


def test_a_path_with_no_file_there_is_none(tmp_path):
    assert tla.stored_file(tmp_path / "piece.tla", "scores/piece.pdf") is None


def test_a_folder_at_the_path_isnt_the_file(tmp_path):
    (tmp_path / "scores").mkdir()
    assert tla.stored_file(tmp_path / "piece.tla", "scores") is None


def test_an_empty_path_is_none_and_isnt_the_files_folder(tmp_path, monkeypatch):
    def no_lookup(path):
        raise AssertionError(f"looked up {path!r}")

    monkeypatch.setattr(os.path, "isfile", no_lookup)
    assert tla.stored_file(tmp_path / "piece.tla", "") is None


@pytest.mark.parametrize(
    "stored",
    ["https://example.com/scores/piece.pdf", "http://youtu.be/_ORrftU6sGA"],
)
def test_a_url_names_no_file_and_is_never_looked_up(tmp_path, monkeypatch, stored):
    def no_lookup(path):
        raise AssertionError(f"looked up {path!r}")

    monkeypatch.setattr(os.path, "isfile", no_lookup)
    assert tla.stored_file(tmp_path / "piece.tla", stored) is None


def test_a_path_of_the_other_systems_form_is_never_looked_up_here(
    tmp_path, monkeypatch
):
    def no_lookup(path):
        raise AssertionError(f"looked up {path!r}")

    other = "/home/someone/piece.pdf" if WINDOWS else "C:/Users/someone/piece.pdf"
    monkeypatch.setattr(os.path, "isfile", no_lookup)
    assert tla.stored_file(tmp_path / "piece.tla", other) is None


# `media` uses it


def test_media_is_found_through_it(tmp_path, monkeypatch):
    doc = tla.new_document()
    doc.media_path = "audio/piece.wav"
    given = []
    sentinel = tmp_path / "from the lookup"

    def lookup(path, stored):
        given.append((path, stored))
        return sentinel

    monkeypatch.setattr(media_files, "stored_file", lookup)
    piece = tmp_path / "piece.tla"
    assert tla.media(piece, doc).path == sentinel
    assert given == [(piece, "audio/piece.wav")]


def test_media_and_the_lookup_agree(tmp_path):
    media = a_file(tmp_path / "audio" / f"{NFD}.wav")
    doc = tla.new_document()
    doc.media_path = f"audio/{NFC}.wav"
    piece = tmp_path / "piece.tla"
    found = tla.media(piece, doc)
    assert found.path == tla.stored_file(piece, doc.media_path)
    assert os.path.samefile(found.path, media)


def test_it_is_public():
    assert "stored_file" in tla.__all__
