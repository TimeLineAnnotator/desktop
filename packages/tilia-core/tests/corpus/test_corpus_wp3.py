"""The index on real ``.tla`` files, through WP3's reader as the default
(TimeLineAnnotator/project-management#154 and #185; contracts/reader.md).

Files of the current format are written with ``tla.write``; old ones are the
files of ``tests/tla/old``, saved by the TiLiA versions they come from."""

import hashlib
import json
import pickle
import shutil
from pathlib import Path

import pytest
from tla_files import song, write

from tilia_core import open_corpus, tla
from tilia_core.corpus import fingerprint, scan
from tilia_core.corpus.tla_reader import TlaReader
from tilia_core.tla import reader as wp3_reader

# The writer's own, not the recording one conftest.py puts in its place during a
# test: these tests compute fingerprints, they don't write files.
from tilia_core.tla.writer import canonical_bytes

OLD = Path(__file__).parents[1] / "tla" / "old"
OLD_FILES = sorted(p.name for p in OLD.glob("*.tla"))
GOLDEN = Path(__file__).parents[1] / "tla" / "golden"
EVERY_FILE = sorted(GOLDEN.glob("*.tla")) + sorted(OLD.glob("*.tla"))


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


# --------------------------------------------------------------------------- #
# Units of kinds the core doesn't know (TimeLineAnnotator/project-management#591)
# --------------------------------------------------------------------------- #
def test_unknown_tla_is_indexed_with_its_known_units_only(tmp_path):
    # Its marker timeline holds a unit whose kind is spelled "marker": TiLiA
    # reads component kinds exactly and knows "MARKER", so it isn't a marker.
    shutil.copyfile(GOLDEN / "unknown.tla", tmp_path / "unknown.tla")
    with opened(tmp_path) as corpus:
        row = corpus.file("unknown.tla")
        assert (row.state, row.reason) == ("readable", None)
        units = unit_keys(corpus, "unknown.tla")
    assert set(units) == {
        "019b76da-a806-7e00-ac14-06fe451fb363",  # BEAT
        "019b76da-a807-727e-a498-f18f1509941f",  # BEAT
        "019b76da-a808-75c1-8240-223b48ef1d65",  # MARKER
    }


# The kinds of the units the index holds, by the names the API gives them,
# which a unit of a kind the core doesn't know can be spelled as, each with the
# kind of timeline that holds it.
INDEXED_UNITS = {
    "hierarchy": "Hierarchy",
    "marker": "Marker",
    "range": "Range",
    "harmony": "Harmony",
    "mode": "Harmony",
    "beat": "Beat",
}


@pytest.mark.parametrize("kind", sorted(INDEXED_UNITS))
def test_a_unit_spelled_as_a_known_kind_s_name_is_left_out(tmp_path, kind):
    data = json.loads((GOLDEN / "every-kind.tla").read_text(encoding="utf-8"))
    timeline = next(
        tl for tl in data["timelines"].values() if tl["kind"] == INDEXED_UNITS[kind]
    )
    spelled = next(
        uid for uid, c in timeline["components"].items() if c["kind"] == kind.upper()
    )
    timeline["components"][spelled]["kind"] = kind
    shutil.copyfile(GOLDEN / "every-kind.tla", tmp_path / "known.tla")
    write(tmp_path / "spelled.tla", data)
    with opened(tmp_path) as corpus:
        row = corpus.file("spelled.tla")
        assert (row.state, row.reason) == ("readable", None)
        known = unit_keys(corpus, "known.tla")
        units = unit_keys(corpus, "spelled.tla")
    assert spelled in known
    assert set(units) == set(known) - {spelled}


# --------------------------------------------------------------------------- #
# The fingerprint the document was read with
# (TimeLineAnnotator/project-management#545)
# --------------------------------------------------------------------------- #
def file_id(path):
    return path.name


def without_media_length(path: Path) -> Path:
    """A file in the current format with units and no media length, whose
    components' states a read keeps until they are looked at."""
    data = song()
    data["media"]["length"] = None
    return write(path, data)


def as_computed_before(path: Path) -> str:
    """The fingerprint the index recorded before it took the document's: the
    SHA-256 of the canonical bytes of the document read, or for an old file of
    the one read with its paths as stored."""
    data = path.read_bytes()
    doc = tla.loads(data, path=path)
    if doc.format_version != tla.FORMAT_VERSION:
        doc = wp3_reader.loads_for_fingerprint(data, path=path)
    return hashlib.sha256(canonical_bytes(doc)).hexdigest()


def scanned(path: Path) -> scan.Outcome:
    """The outcome of reading ``path`` as a scan reads it, which a worker
    process pickles back to the scan."""
    info = path.stat()
    found = scan.Found(path.name, path, info.st_size, info.st_mtime_ns)
    outcome = scan.read_file(TlaReader(), found)
    assert outcome.readable, outcome.reason
    return outcome


@pytest.mark.parametrize("source", EVERY_FILE, ids=file_id)
def test_the_fingerprint_a_scan_reads_is_unchanged(tmp_path, source):
    path = tmp_path / source.name
    shutil.copyfile(source, path)
    read = scanned(path).fingerprint
    assert read == as_computed_before(path) == tla.fingerprint(path)


@pytest.mark.parametrize("source", EVERY_FILE, ids=file_id)
def test_the_index_s_fingerprints_are_unchanged(tmp_path, source):
    path = tmp_path / source.name
    shutil.copyfile(source, path)
    with opened(tmp_path) as corpus:
        recorded = corpus.file(source.name).fingerprint
    assert recorded == as_computed_before(path) == tla.fingerprint(path)


def every_kind_of_file(tmp_path: Path) -> list[Path]:
    """Every golden and old file, and one without a media length."""
    paths = [without_media_length(tmp_path / "no-length.tla")]
    for source in EVERY_FILE:
        paths.append(tmp_path / source.name)
        shutil.copyfile(source, paths[-1])
    return paths


def test_a_scanned_document_carries_no_file_bytes_once_read(tmp_path):
    for path in every_kind_of_file(tmp_path):
        outcome = scanned(path)
        assert path.read_bytes() not in pickle.dumps(outcome), path.name


def test_a_scanned_document_has_the_fingerprint_and_states_it_was_read_with(
    tmp_path,
):
    # What a write of the core's document would state and compare: the index's
    # fingerprint, and the components' states with no media length.
    for path in every_kind_of_file(tmp_path):
        outcome = scanned(path)
        source = outcome.document.source
        assert source.fingerprint == outcome.fingerprint == tla.fingerprint(path)
        # As tla makes them itself, from the bytes, not as the reader does.
        assert dict(source.read_unmeasured) == dict(tla.read(path).read_unmeasured)
    no_length = scanned(tmp_path / "no-length.tla").document.source
    assert len(no_length.read_unmeasured) == 6, "one state for each unit"


def test_a_scan_parses_a_current_file_once_and_migrates_an_old_one_twice(
    tmp_path, monkeypatch
):
    # An old file's fingerprint is that of its migration with its paths as
    # stored, which WP3 makes from the bytes read: a second migration. Nothing
    # else is parsed again, not even the states of a file with no media length.
    without_media_length(tmp_path / "current.tla")
    shutil.copyfile(OLD / "0.7.0.tla", tmp_path / "old.tla")
    parsed, migrated = [], []
    real_parse, real_migrate = wp3_reader.parse, wp3_reader.migrate

    def parse(data, *args, path=None, **kwargs):
        parsed.append(Path(path).name)
        return real_parse(data, *args, path=path, **kwargs)

    def migrate(content, *args, path=None, **kwargs):
        migrated.append(Path(path).name)
        return real_migrate(content, *args, path=path, **kwargs)

    monkeypatch.setattr(wp3_reader, "parse", parse)
    monkeypatch.setattr(wp3_reader, "migrate", migrate)
    with opened(tmp_path) as corpus:
        assert {row.path for row in corpus.files()} == {"current.tla", "old.tla"}
    assert sorted(parsed) == ["current.tla", "old.tla", "old.tla"]
    assert migrated == ["old.tla", "old.tla"]


def test_the_reader_reads_any_old_file_with_the_core_document_kept(tmp_path):
    for name in OLD_FILES:
        document = TlaReader().read(OLD / name)
        assert document.source.document_id == document.document_id
        assert [t.ordinal for t in document.timelines] == sorted(
            t.ordinal for t in document.timelines
        )
