"""The index kept on disk between runs (corpus/cache.py): a corpus opened
again from its copy is the one a first build gives, reading only the files
that changed since."""

import dataclasses
import os
import sqlite3
import time
from pathlib import Path

import corpus_docs
import examples
import pytest
from json_reader import JsonDocumentReader
from tla_files import as_tla

from tilia_core import open_corpus, tla, tql
from tilia_core.commands import query
from tilia_core.corpus import cache
from tilia_core.corpus.tla_reader import TlaReader

DATA = examples.load()
FIXTURES = sorted(DATA["fixtures"])
HOUR = 3600


@pytest.fixture
def copies(tmp_path, monkeypatch):
    """The folder the copies go to, instead of the user's cache folder."""
    where = tmp_path / "copies"
    monkeypatch.setenv(cache.ENV, str(where))
    return where


@pytest.fixture
def reads(monkeypatch):
    """The names of the files the default reader reads."""
    read = TlaReader.read
    names = []

    def counted(self, path):
        names.append(Path(path).name)
        return read(self, path)

    monkeypatch.setattr(TlaReader, "read", counted)
    return names


def _settle(*paths):
    """Date the files an hour back: a file written just now is racy, and a
    rescan reads it again whatever its size and date (FR-024)."""
    then = time.time() - HOUR
    for path in paths:
        os.utime(path, (then, then))


def _write(folder: Path, name: str) -> Path:
    fixture = DATA["fixtures"][name]
    path = folder / f"{name}.tla"
    tla.write(path, as_tla(corpus_docs.document_from_fixture(fixture)))
    _settle(path)
    return path


@pytest.fixture
def folder(tmp_path):
    """Every fixture of ``examples.toml`` as a ``.tla`` file, with harmonies
    and bars."""
    pytest.importorskip("music21", reason="the writer checks chords with music21")
    where = tmp_path / "corpus"
    where.mkdir()
    for name in FIXTURES:
        _write(where, name)
    return where


def _tables(corpus) -> dict[str, list[tuple]]:
    with corpus.reading() as r:
        con = r.connection
        names = [
            n
            for (n,) in con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        return {n: sorted(con.execute(f"SELECT * FROM {n}"), key=repr) for n in names}


def _fields(time_map) -> dict:
    """A time map's fields: WP9's time maps compare by identity."""
    return {f.name: getattr(time_map, f.name) for f in dataclasses.fields(time_map)}


def _report(corpus):
    r = corpus.open_report
    return (r.added, r.unreadable, r.shared_ids, r.error)


def _result(corpus, text):
    try:
        got = tql.run(corpus, text)
    except tql.TQLError as err:
        return ("error", str(err))
    return (got.grain, got.columns, got.rows, got.warnings, len(got.matches))


def test_a_corpus_opened_again_is_the_one_a_build_gives(folder, copies, reads):
    with open_corpus(folder, rescan_before_reads=False) as built:
        with open_corpus(folder, rescan_before_reads=False, keep_on_disk=True):
            pass
        assert len(list(copies.iterdir())) == 1
        reads.clear()
        with open_corpus(folder, rescan_before_reads=False, keep_on_disk=True) as kept:
            assert reads == []
            assert _tables(kept) == _tables(built)
            assert _report(kept) == _report(built)
            assert kept.generation == built.generation == 1
            keys = [f.id for f in built.files()]
            mapped = [k for k in keys if built.time_map(k) is not None]
            assert mapped  # the fixtures with beats have bars
            for key in keys:
                tmap = kept.time_map(key)
                if built.time_map(key) is None:
                    assert tmap is None
                else:
                    assert isinstance(tmap, cache.LazyTimeMap)
                    assert tmap.timeline_id == built.time_map(key).timeline_id
                    assert _fields(tmap.built()) == _fields(built.time_map(key))


def test_every_example_runs_the_same_on_a_corpus_opened_again(folder, copies):
    with open_corpus(folder, rescan_before_reads=False, keep_on_disk=True):
        pass
    with (
        open_corpus(folder, rescan_before_reads=False) as built,
        open_corpus(folder, rescan_before_reads=False, keep_on_disk=True) as kept,
    ):
        for example in DATA["examples"]:
            assert _result(kept, example.query) == _result(
                built, example.query
            ), example.n


def test_opening_again_reads_only_the_changed_and_new_files(folder, copies, reads):
    with open_corpus(folder, rescan_before_reads=False, keep_on_disk=True):
        pass
    first, second, *_ = FIXTURES
    changed = folder / f"{first}.tla"
    changed.write_bytes(changed.read_bytes() + b"\n")  # another size
    _settle(changed)
    (folder / f"{second}.tla").unlink()
    (folder / "sub").mkdir()
    added = folder / "sub" / f"{second}.tla"
    _write(folder / "sub", second)
    reads.clear()
    with open_corpus(folder, rescan_before_reads=False, keep_on_disk=True) as kept:
        assert sorted(reads) == sorted([changed.name, added.name])
        with open_corpus(folder, rescan_before_reads=False) as built:
            assert _report(kept) == _report(built)
            assert sorted(f.path for f in kept.files()) == sorted(
                f.path for f in built.files()
            )
            for example in DATA["examples"][:40]:
                assert _result(kept, example.query) == _result(built, example.query)
    assert "unavailable" not in str(_report(kept))


def test_a_change_seen_while_open_is_kept_when_the_corpus_closes(folder, copies, reads):
    name = FIXTURES[0]
    with open_corpus(folder, rescan_before_reads=False, keep_on_disk=True) as opened:
        (folder / f"{name}.tla").unlink()
        assert opened.scan().unavailable == (f"{name}.tla",)
    reads.clear()
    with open_corpus(folder, rescan_before_reads=False, keep_on_disk=True) as kept:
        assert reads == []
        assert f"{name}.tla" not in [f.path for f in kept.files()]


def test_an_unreadable_file_is_reported_on_every_opening(folder, copies, reads):
    (folder / "broken.tla").write_text("{ not json", encoding="utf-8")
    _settle(folder / "broken.tla")
    with open_corpus(folder, rescan_before_reads=False, keep_on_disk=True) as first:
        built = first.open_report.unreadable
    assert [path for path, _, _ in built] == ["broken.tla"]
    reads.clear()
    with open_corpus(folder, rescan_before_reads=False, keep_on_disk=True) as kept:
        assert reads == []
        assert kept.open_report.unreadable == built


def test_a_copy_written_by_other_code_is_thrown_away(
    folder, copies, reads, monkeypatch
):
    with open_corpus(folder, rescan_before_reads=False, keep_on_disk=True):
        pass
    monkeypatch.setattr(cache, "stamp", lambda: "other code")
    reads.clear()
    with open_corpus(folder, rescan_before_reads=False, keep_on_disk=True):
        assert len(reads) == len(FIXTURES)
    reads.clear()
    with open_corpus(folder, rescan_before_reads=False, keep_on_disk=True):
        assert reads == []  # the copy written again, with the new stamp


@pytest.mark.parametrize(
    "damage",
    [
        lambda path: path.write_bytes(b"not a database"),
        lambda path: path.write_bytes(path.read_bytes()[:4096]),
        lambda path: _drop_files_table(path),
    ],
    ids=["garbage", "cut short", "missing table"],
)
def test_a_damaged_copy_is_thrown_away(folder, copies, reads, damage):
    with open_corpus(folder, rescan_before_reads=False) as built:
        expected = _tables(built)
    with open_corpus(folder, rescan_before_reads=False, keep_on_disk=True):
        pass
    (path,) = copies.iterdir()
    damage(path)
    reads.clear()
    with open_corpus(folder, rescan_before_reads=False, keep_on_disk=True) as kept:
        assert len(reads) == len(FIXTURES)
        assert _tables(kept) == expected
    reads.clear()
    with open_corpus(folder, rescan_before_reads=False, keep_on_disk=True):
        assert reads == []


def _drop_files_table(path):
    con = sqlite3.connect(path)
    con.execute("DROP TABLE tilia_cache_files")
    con.commit()
    con.close()


def test_nothing_is_kept_unless_asked(folder, copies):
    with open_corpus(folder, rescan_before_reads=False):
        pass
    assert not copies.exists()


def test_nothing_is_kept_when_the_variable_is_off(folder, monkeypatch, tmp_path):
    monkeypatch.setenv(cache.ENV, "off")
    assert cache.path_for(folder) is None
    with open_corpus(folder, rescan_before_reads=False, keep_on_disk=True):
        pass
    assert not (tmp_path / "copies").exists()


def test_another_reader_keeps_nothing(tmp_path, copies):
    corpus_docs.write_doc(tmp_path / "song.json", corpus_docs.document())
    with open_corpus(
        tmp_path,
        rescan_before_reads=False,
        reader=JsonDocumentReader(),
        keep_on_disk=True,
    ):
        pass
    assert not copies.exists()


def test_each_folder_has_a_copy_of_its_own(tmp_path, copies):
    pytest.importorskip("music21", reason="the writer checks chords with music21")
    for name in ("one", "two"):
        (tmp_path / name).mkdir()
        _write(tmp_path / name, FIXTURES[0])
        with open_corpus(tmp_path / name, rescan_before_reads=False, keep_on_disk=True):
            pass
    assert len(list(copies.iterdir())) == 2


def test_the_query_command_reads_the_files_once(folder, copies, reads, capsys):
    text = "* IN form"
    assert query.main([str(folder), text]) == 0
    first = capsys.readouterr().out
    assert reads
    reads.clear()
    assert query.main([str(folder), text]) == 0
    assert capsys.readouterr().out == first
    assert reads == []
