"""The walk of a corpus folder, the files' records and the first build
(research R6, R8; TimeLineAnnotator/project-management#122)."""

import hashlib
import logging
import os
import sys
import unicodedata
from pathlib import Path

import corpus_docs
import pytest
from json_reader import JsonDocumentReader

from tilia_core.corpus import scan
from tilia_core.corpus.settings import NoSettings
from tilia_core.corpus.store import Store

READER = JsonDocumentReader()


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    """Retries without the pause; the test of the pause records it."""
    pauses = []
    monkeypatch.setattr(scan, "sleep", pauses.append)
    return pauses


def doc(name, label="x"):
    return corpus_docs.document(
        corpus_docs.markers([[label, 1]], tid="m", ordinal=1), document_id=name
    )


def write(folder, relpath, name=None, **kw):
    return corpus_docs.write_doc(folder / relpath, doc(name or relpath), **kw)


def built(folder, reader=READER):
    scanner = scan.Scanner(folder, Store(), reader, NoSettings())
    report = scanner.build()
    return scanner, report


def files_table(scanner):
    with scanner.store.reading() as r:
        return r.connection.execute(
            "SELECT id, path, document_id, state, reason, fingerprint FROM files "
            "ORDER BY id"
        ).fetchall()


class CountingReader(JsonDocumentReader):
    """The stand-in, counting its reads by file name, and raising ``error``
    for the names in ``failing``."""

    def __init__(self, failing=(), error=None):
        self.reads = []
        self.failing = set(failing)
        self.error = error

    def read(self, path):
        self.reads.append(Path(path).name)
        if Path(path).name in self.failing:
            raise self.error
        return super().read(path)


# --------------------------------------------------------------------------- #
# The walk
# --------------------------------------------------------------------------- #
def test_subfolders_are_taken_in(tmp_path):
    write(tmp_path, "a.tla")
    write(tmp_path, "sub/b.tla")
    write(tmp_path, "sub/deeper/c.tla")
    found = scan.walk(tmp_path, READER, NoSettings())
    assert [f.path for f in found] == ["a.tla", "sub/b.tla", "sub/deeper/c.tla"]
    assert found[1].native == tmp_path / "sub" / "b.tla"


def test_hidden_files_and_folders_are_skipped(tmp_path):
    write(tmp_path, "a.tla")
    write(tmp_path, ".x.tla")
    write(tmp_path, ".hidden/b.tla")
    assert [f.path for f in scan.walk(tmp_path, READER, NoSettings())] == ["a.tla"]


def test_the_extension_in_any_letter_case_is_taken_in(tmp_path):
    write(tmp_path, "A.TLA")
    write(tmp_path, "b.Tla")
    write(tmp_path, "c.json")
    paths = [f.path for f in scan.walk(tmp_path, READER, NoSettings())]
    assert paths == ["A.TLA", "b.Tla"]


def test_a_temporary_file_is_skipped(tmp_path):
    write(tmp_path, "x.tla")
    write(tmp_path, "x.tmp.tla")
    write(tmp_path, "y.TMP.TLA")
    assert [f.path for f in scan.walk(tmp_path, READER, NoSettings())] == ["x.tla"]


def test_a_link_to_a_folder_is_not_followed(tmp_path):
    corpus, elsewhere = tmp_path / "corpus", tmp_path / "elsewhere"
    write(corpus, "a.tla")
    write(elsewhere, "b.tla")
    try:
        os.symlink(elsewhere, corpus / "link", target_is_directory=True)
        # a link to a folder named like a file is no file either
        os.symlink(elsewhere, corpus / "folder.tla", target_is_directory=True)
    except (OSError, NotImplementedError) as err:
        pytest.skip(f"this system can't create a link to a folder: {err}")
    assert [f.path for f in scan.walk(corpus, READER, NoSettings())] == ["a.tla"]


@pytest.mark.skipif(sys.platform != "win32", reason="directory junctions are Windows'")
def test_a_directory_junction_is_not_followed(tmp_path):
    import _winapi

    corpus, elsewhere = tmp_path / "corpus", tmp_path / "elsewhere"
    write(corpus, "a.tla")
    write(elsewhere, "b.tla")
    _winapi.CreateJunction(str(elsewhere), str(corpus / "junction"))
    assert (corpus / "junction" / "b.tla").exists()  # it is a junction
    assert [f.path for f in scan.walk(corpus, READER, NoSettings())] == ["a.tla"]


def test_a_folder_that_cant_be_listed_is_logged_and_skipped(
    tmp_path, monkeypatch, caplog
):
    write(tmp_path, "a.tla")
    write(tmp_path, "locked/b.tla")
    write(tmp_path, "z.tla")
    real = os.scandir
    locked = tmp_path / "locked"

    def scandir(path="."):
        if Path(path) == locked:
            raise PermissionError(13, "Permission denied", str(path))
        return real(path)

    monkeypatch.setattr(os, "scandir", scandir)
    with caplog.at_level(logging.WARNING, logger=scan.__name__):
        found = scan.walk(tmp_path, READER, NoSettings())
    assert [f.path for f in found] == ["a.tla", "z.tla"]
    assert any("locked" in r.getMessage() for r in caplog.records)


def test_the_corpus_folder_that_cant_be_listed_raises(tmp_path, monkeypatch):
    real = os.scandir

    def scandir(path="."):
        if Path(path) == tmp_path:
            raise PermissionError(13, "Permission denied", str(path))
        return real(path)

    monkeypatch.setattr(os, "scandir", scandir)
    with pytest.raises(PermissionError):
        scan.walk(tmp_path, READER, NoSettings())


def test_paths_are_relative_with_slashes_in_nfc(tmp_path):
    write(tmp_path, unicodedata.normalize("NFD", "Café/Ünd.tla"))
    assert unicodedata.normalize("NFD", "Ünd.tla") in os.listdir(
        tmp_path / unicodedata.normalize("NFD", "Café")
    )
    (found,) = scan.walk(tmp_path, READER, NoSettings())
    assert found.path == unicodedata.normalize("NFC", "Café/Ünd.tla")
    scanner, _ = built(tmp_path)
    assert list(scanner.records) == [found.path]
    assert scanner.records[found.path].state == "readable"  # the native path opens
    assert files_table(scanner)[0][1] == found.path


# --------------------------------------------------------------------------- #
# Reading, the records and the build
# --------------------------------------------------------------------------- #
def test_files_are_read_in_sorted_path_order_and_keyed_in_it(tmp_path):
    for path in ("b.tla", "a/x.tla", "a.tla", "c/d/e.tla"):
        write(tmp_path, path)
    reader = CountingReader()
    scanner, report = built(tmp_path, reader)
    order = ["a.tla", "a/x.tla", "b.tla", "c/d/e.tla"]
    assert [Path(p).name for p in order] == reader.reads
    keys = [scanner.records[p].key for p in order]
    assert keys == sorted(keys)
    assert report.added == tuple(order)
    # a fresh build of the same folder gives the same keys
    again, _ = built(tmp_path)
    assert files_table(again) == files_table(scanner)


def test_the_build_fills_the_index_at_generation_1(tmp_path):
    write(tmp_path, "a.tla")
    write(tmp_path, "b.tla")
    scanner, report = built(tmp_path)
    assert (report.generation_before, report.generation_after) == (0, 1)
    assert scanner.store.generation == 1
    with scanner.store.reading() as r:
        labels = r.connection.execute("SELECT label FROM components").fetchall()
    assert labels == [("x",), ("x",)]


def test_a_record_holds_what_data_model_lists(tmp_path):
    path = write(tmp_path, "sub/a.tla", name="doc-a")
    scanner, _ = built(tmp_path)
    rec = scanner.records["sub/a.tla"]
    info = path.stat()
    assert (rec.path, rec.native) == ("sub/a.tla", path)
    assert (rec.size, rec.mtime_ns) == (info.st_size, info.st_mtime_ns)
    assert rec.read_at_ns is not None and rec.read_at_ns > 0
    assert (rec.state, rec.reason, rec.os_error) == ("readable", None, False)
    assert rec.document_id == "doc-a"
    assert rec.fingerprint == hashlib.sha256(path.read_bytes()).hexdigest()
    assert files_table(scanner) == [
        (rec.key, "sub/a.tla", "doc-a", "readable", None, rec.fingerprint)
    ]


def test_the_fingerprint_ignores_line_endings_bom_and_key_order(tmp_path):
    write(tmp_path, "a.tla", name="same")
    write(tmp_path, "b.tla", name="same", crlf=True, bom=True, shuffle_keys=True)
    scanner, report = built(tmp_path)
    a, b = scanner.records["a.tla"], scanner.records["b.tla"]
    assert a.fingerprint == b.fingerprint
    assert report.shared_ids == (("a.tla", "b.tla"),)


def test_a_broken_file_is_unreadable_with_its_line_after_one_retry(tmp_path, no_pause):
    write(tmp_path, "a.tla")
    (tmp_path / "broken.tla").write_text('{\n  "document_id": "x",\n  oops\n}')
    reader = CountingReader()
    scanner, report = built(tmp_path, reader)
    assert reader.reads.count("broken.tla") == 2
    assert reader.reads.count("a.tla") == 1
    assert no_pause == [scan.READ_RETRY_PAUSE] == [0.2]
    rec = scanner.records["broken.tla"]
    assert (rec.state, rec.line, rec.os_error) == ("unreadable", 3, False)
    assert rec.reason.startswith("can't read (line 3): ")
    assert report.unreadable == (("broken.tla", 3, rec.reason),)
    assert report.added == ("a.tla", "broken.tla")
    rows = {r[1]: r for r in files_table(scanner)}
    assert rows["broken.tla"][2:] == (None, "unreadable", rec.reason, None)
    assert rows["a.tla"][3] == "readable"


def test_a_file_read_again_on_the_retry_is_readable(tmp_path):
    write(tmp_path, "a.tla")

    class FailsOnce(JsonDocumentReader):
        tries = 0

        def read(self, path):
            self.tries += 1
            if self.tries == 1:
                raise PermissionError(13, "Permission denied")
            return super().read(path)

    scanner, report = built(tmp_path, FailsOnce())
    assert scanner.records["a.tla"].state == "readable"
    assert report.unreadable == ()


def test_a_file_that_cant_be_opened_is_unreadable_with_the_systems_message(tmp_path):
    write(tmp_path, "a.tla")
    write(tmp_path, "b.tla")
    reader = CountingReader({"a.tla"}, PermissionError(13, "Permission denied"))
    scanner, report = built(tmp_path, reader)
    rec = scanner.records["a.tla"]
    assert reader.reads.count("a.tla") == 2
    assert (rec.state, rec.os_error) == ("unreadable", True)
    assert rec.reason == "can't read: Permission denied"
    assert report.unreadable == (("a.tla", None, rec.reason),)
    assert scanner.records["b.tla"].state == "readable"


def test_any_other_error_of_the_reader_makes_the_file_unreadable_and_is_logged(
    tmp_path, caplog
):
    for name in ("a.tla", "b.tla", "c.tla"):
        write(tmp_path, name)
    reader = CountingReader({"b.tla"}, KeyError("timelines"))
    with caplog.at_level(logging.ERROR, logger=scan.__name__):
        scanner, report = built(tmp_path, reader)
    rec = scanner.records["b.tla"]
    assert (rec.state, rec.os_error) == ("unreadable", False)
    assert rec.reason == "can't read: KeyError: 'timelines'"
    (logged,) = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert logged.exc_info is not None and logged.exc_info[0] is KeyError
    assert "b.tla" in logged.getMessage()
    assert [scanner.records[p].state for p in ("a.tla", "c.tla")] == ["readable"] * 2
    with scanner.store.reading() as r:
        n = r.connection.execute("SELECT count(*) FROM components").fetchone()[0]
    assert n == 2


def test_an_empty_folder_builds_an_empty_index(tmp_path):
    scanner, report = built(tmp_path)
    assert not report
    assert scanner.records == {}
    assert files_table(scanner) == []
    assert scanner.store.generation == 0
