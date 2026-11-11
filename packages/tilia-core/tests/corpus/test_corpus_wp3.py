"""The index on real ``.tla`` files, through WP3's reader as the default
(TimeLineAnnotator/project-management#154 and #185; contracts/reader.md).

Files of the current format are written with ``tla.write``; old ones are the
files of ``tests/tla/old``, saved by the TiLiA versions they come from."""

import shutil
from pathlib import Path

import pytest
from tla_files import song, write

from tilia_core import open_corpus, tla
from tilia_core.corpus import fingerprint
from tilia_core.corpus.tla_reader import TlaReader

OLD = Path(__file__).parents[1] / "tla" / "old"
OLD_FILES = sorted(p.name for p in OLD.glob("*.tla"))


def opened(folder, **kw):
    kw.setdefault("rescan_before_reads", False)
    return open_corpus(folder, **kw)


def written(path: Path, label: str = "verse") -> Path:
    """A file the core's writer wrote."""
    doc = tla.loads(write(path.with_suffix(".json"), song(label)).read_bytes())
    path.with_suffix(".json").unlink()
    tla.write(path, doc)
    return path


def ids(corpus, path: str) -> tuple:
    """The file's document id, and its timelines' and units' ids in the file."""
    with corpus.reading() as r:
        con = r.connection
        (file_id, document_id) = con.execute(
            "SELECT id, document_id FROM files WHERE path = ?", (path,)
        ).fetchone()
        timelines = con.execute(
            "SELECT uuid FROM timelines WHERE file_id = ? ORDER BY ordinal", (file_id,)
        ).fetchall()
        units = con.execute(
            "SELECT uuid FROM components WHERE file_id = ? ORDER BY uuid", (file_id,)
        ).fetchall()
    return document_id, tuple(timelines), tuple(units)


def unit_keys(corpus, path: str) -> dict[str, int]:
    with corpus.reading() as r:
        return dict(
            r.connection.execute(
                "SELECT c.uuid, c.id FROM components c JOIN files f "
                "ON f.id = c.file_id WHERE f.path = ?",
                (path,),
            ).fetchall()
        )


def test_open_corpus_reads_real_files_with_no_reader_given(tmp_path):
    written(tmp_path / "song.tla")
    with opened(tmp_path) as corpus:
        (row,) = corpus.files()
        assert (row.path, row.state) == ("song.tla", "readable")
        assert row.format_version == tla.FORMAT_VERSION
        assert row.timeline_kinds == {
            "hierarchy": 1,
            "marker": 1,
            "beat": 1,
            "range": 1,
        }
        with corpus.reading() as r:
            labels = r.connection.execute(
                "SELECT label FROM components WHERE kind = 'hierarchy' ORDER BY start"
            ).fetchall()
        assert labels == [("verse",), ("chorus",)]


def test_the_index_keeps_the_ids_the_file_stores(tmp_path):
    path = written(tmp_path / "song.tla")
    doc = tla.read(path)
    with opened(tmp_path) as corpus:
        document_id, timelines, units = ids(corpus, "song.tla")
    assert document_id == doc.document_id
    by_ordinal = sorted(doc.timelines.values(), key=lambda t: t.ordinal)
    assert timelines == tuple((t.id,) for t in by_ordinal)
    assert units == tuple(
        sorted((c,) for t in doc.timelines.values() for c in t.components)
    )


@pytest.mark.parametrize("name", OLD_FILES)
def test_the_scan_records_wp3s_fingerprint(tmp_path, name):
    path = tmp_path / name
    shutil.copyfile(OLD / name, path)
    with opened(tmp_path) as corpus:
        assert corpus.file(name).fingerprint == tla.fingerprint(path)


def test_the_fingerprint_with_no_reader_given_is_wp3s(tmp_path):
    current = written(tmp_path / "song.tla")
    old = tmp_path / "old.tla"
    shutil.copyfile(OLD / "0.7.0.tla", old)
    assert fingerprint(current) == tla.fingerprint(current)
    assert fingerprint(old) == tla.fingerprint(old)


def test_a_copy_with_crlf_line_endings_has_the_same_fingerprint(tmp_path):
    path = written(tmp_path / "song.tla")
    data = path.read_bytes()
    assert b"\r\n" not in data
    (tmp_path / "crlf.tla").write_bytes(data.replace(b"\n", b"\r\n"))
    with opened(tmp_path) as corpus:
        lf, crlf = corpus.file("song.tla"), corpus.file("crlf.tla")
        assert crlf.state == "readable"
        assert crlf.fingerprint == lf.fingerprint == tla.fingerprint(path)


@pytest.mark.parametrize("name", OLD_FILES)
def test_an_old_file_gives_the_same_ids_at_every_read(tmp_path, name):
    shutil.copyfile(OLD / name, tmp_path / name)
    with opened(tmp_path) as corpus:
        first = ids(corpus, name)
    with opened(tmp_path) as corpus:
        assert ids(corpus, name) == first
        corpus.reread(tmp_path / name)
        assert ids(corpus, name) == first
    assert first[1], "the file has timelines"


@pytest.mark.parametrize("name", OLD_FILES)
def test_a_moved_old_file_is_seen_as_a_move(tmp_path, name):
    shutil.copyfile(OLD / name, tmp_path / name)
    with opened(tmp_path) as corpus:
        key = corpus.file(name).id
        units = unit_keys(corpus, name)
        (tmp_path / "elsewhere" / "deeper").mkdir(parents=True)
        moved = f"elsewhere/deeper/{name}"
        shutil.move(tmp_path / name, tmp_path / moved)
        report = corpus.scan()
        assert report.moved == ((name, moved),)
        assert not (report.added or report.unavailable)
        assert corpus.file(moved).id == key
        assert unit_keys(corpus, moved) == units


def test_broken_json_is_unreadable_with_its_line(tmp_path):
    (tmp_path / "broken.tla").write_text(
        '{\n  "version": "1.0.0",\n  "app_name": ,\n}\n'
    )
    with opened(tmp_path) as corpus:
        row = corpus.file("broken.tla")
    assert row.state == "unreadable"
    assert "line 3" in row.reason


def test_a_newer_format_is_unreadable_and_says_so(tmp_path):
    data = song()
    data["version"] = "99.0.0"
    write(tmp_path / "newer.tla", data)
    with opened(tmp_path) as corpus:
        row = corpus.file("newer.tla")
    assert row.state == "unreadable"
    assert "99.0.0" in row.reason


def test_the_reader_skips_wp3s_temporary_files():
    reader = TlaReader()
    assert reader.extensions == (".tla",)
    assert reader.is_temporary(".song.tla.0123abcd.tmp")
    assert not reader.is_temporary("song.tla")


def test_the_reader_reads_any_old_file_with_the_core_document_kept(tmp_path):
    for name in OLD_FILES:
        document = TlaReader().read(OLD / name)
        assert document.source.document_id == document.document_id
        assert [t.ordinal for t in document.timelines] == sorted(
            t.ordinal for t in document.timelines
        )
