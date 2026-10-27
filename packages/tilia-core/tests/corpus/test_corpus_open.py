"""Opening a folder as a corpus (User Story 1; contracts/corpus.md)."""

import dataclasses
import os
from pathlib import Path

import corpus_docs
import pytest
from grammars import GRAMMARS
from json_reader import JsonDocumentReader

import tilia_core
from tilia_core import open_corpus, tql
from tilia_core.corpus import (
    ComponentRow,
    Corpus,
    FileDetail,
    FileRow,
    ScanReport,
    TimelineRow,
    scan,
)
from tilia_core.corpus.settings import NoSettings

READER = JsonDocumentReader()


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(scan, "sleep", lambda seconds: None)


def opened(folder, **kw):
    kw.setdefault("reader", READER)
    return open_corpus(folder, **kw)


def song(name, labels=("verse", "chorus")):
    units = [[label, 1, 10 * i, 10 * (i + 1)] for i, label in enumerate(labels)]
    return corpus_docs.document(
        corpus_docs.hierarchy(units, fields={"role": "form"}), document_id=name
    )


def broken_at_line_12(path):
    lines = ["{"] + [f'  "k{n}": {n},' for n in range(1, 11)] + ["  oops", "}"]
    path.write_text("\n".join(lines), encoding="utf-8")


def test_open_corpus_is_exported_from_the_package():
    assert tilia_core.open_corpus is open_corpus


# --------------------------------------------------------------------------- #
# User Story 1
# --------------------------------------------------------------------------- #
def test_scenario_1_three_readable_files_and_one_broken_at_line_12(tmp_path):
    for name in ("a", "b", "c"):
        corpus_docs.write_doc(tmp_path / f"{name}.tla", song(name))
    broken_at_line_12(tmp_path / "d.tla")
    with opened(tmp_path) as corpus:
        rows = {f.path: f for f in corpus.files()}
        assert [rows[p].state for p in ("a.tla", "b.tla", "c.tla")] == ["readable"] * 3
        assert rows["d.tla"].state == "unreadable"
        assert rows["d.tla"].reason.startswith("can't read (line 12): ")
        assert corpus.open_report.unreadable == (("d.tla", 12, rows["d.tla"].reason),)
        assert corpus.open_report.added == ("a.tla", "b.tla", "c.tla", "d.tla")
        with corpus.reading() as r:
            per_file = r.connection.execute(
                "SELECT f.path, count(*) FROM components c JOIN files f "
                "ON f.id = c.file_id GROUP BY f.path ORDER BY f.path"
            ).fetchall()
        assert per_file == [("a.tla", 2), ("b.tla", 2), ("c.tla", 2)]
        assert rows["d.tla"].fields == {} and rows["d.tla"].timeline_kinds == {}


def test_scenario_2_a_two_level_hierarchy_has_parents_depths_and_categories(tmp_path):
    units = [["A", 2, 0, 20], ["verse", 1, 0, 10], ["bridge.modern", 1, 10, 20]]
    doc = corpus_docs.document(corpus_docs.hierarchy(units), document_id="h")
    corpus_docs.write_doc(tmp_path / "h.tla", doc)

    class DeClercq(NoSettings):
        def grammar(self, timeline, document):
            return GRAMMARS["de Clercq"]

    for settings, want in (
        (
            None,
            {
                "A": [("a", None)],
                "verse": [("verse", None)],
                "bridge.modern": [("bridge.modern", None)],
            },
        ),
        (
            DeClercq(),
            {
                "A": [("a", None)],
                "verse": [("verse", None)],
                "bridge.modern": [("bridge.modern", "bridge")],
            },
        ),
    ):
        with opened(tmp_path, settings=settings) as corpus:
            (f,) = corpus.files()
            (tl,) = corpus.file_detail(f.id).timelines
            a, verse, bridge = corpus.components(f.id, [tl.id])
            assert (a.properties["depth"], a.properties["parent_id"]) == (1, None)
            for child in (verse, bridge):
                assert child.properties["parent_id"] == a.id
                assert child.properties["depth"] == 2
            with corpus.reading() as r:
                got = {}
                for label, cat, sup in r.connection.execute(
                    "SELECT c.label, x.category, x.supertype FROM categories x "
                    "JOIN components c ON c.id = x.component_id"
                ):
                    got.setdefault(label, []).append((cat, sup))
            assert got == want


def test_scenario_3_chords_and_keys_have_spans_keys_in_force_and_properties(tmp_path):
    corpus_docs.write_doc(tmp_path / "a.tla", corpus_docs.every_kind(document_id="a"))
    with opened(tmp_path) as corpus:
        (f,) = corpus.files()
        harmony = [t for t in corpus.file_detail(f.id).timelines if t.kind == "harmony"]
        units = corpus.components(f.id, [harmony[0].id])
        keys = {u.uuid: u for u in units if u.kind == "key"}
        chords = [u for u in units if u.kind == "chord"]
        assert [(c.start, c.end) for c in chords] == [(0, 5), (5, 10), (10, 60)]
        assert [(k.start, k.end) for k in keys.values()] == [(0, 10), (10, 60)]
        assert [c.properties["key_id"] for c in chords] == [
            keys["t4:k1"].id,
            keys["t4:k1"].id,
            keys["t4:k2"].id,
        ]
        assert [
            (
                c.properties["root"],
                c.properties["roman"],
                c.properties["symbol"],
                c.properties["key"],
            )
            for c in chords
        ] == [("C", "I", "C", "C"), ("G", "V65", "G7/B", "C"), ("G", "i", "Gm", "g")]
        assert keys["t4:k2"].properties == {
            "step": 4,
            "accidental": 0,
            "mode": "minor",
            "tonic": "G",
            "key": "g",
        }


def test_scenario_5_every_timeline_is_listed_whatever_its_kind(tmp_path):
    doc = corpus_docs.document(
        corpus_docs.markers([["PAC", 5]], tid="m", ordinal=1),
        corpus_docs.unindexed("score", tid="s", ordinal=2),
        corpus_docs.unindexed("pdf", tid="p", ordinal=3, path="score.pdf"),
        corpus_docs.unindexed("audiowave", tid="w", ordinal=4),
        corpus_docs.unindexed("slider", tid="l", ordinal=5),
        corpus_docs.unindexed("spectrogram", tid="x", ordinal=6, name="Spectra"),
        document_id="kinds",
    )
    corpus_docs.write_doc(tmp_path / "k.tla", doc)
    with opened(tmp_path) as corpus:
        (f,) = corpus.files()
        detail = corpus.file_detail(f.id)
        assert [(t.kind, t.name) for t in detail.timelines] == [
            ("marker", "Cadences"),
            ("score", "Score"),
            ("pdf", "Pdf"),
            ("audiowave", "Audiowave"),
            ("slider", "Slider"),
            ("spectrogram", "Spectra"),
        ]
        units = corpus.components(f.id, [t.id for t in detail.timelines])
        assert [(u.kind, u.label) for u in units] == [("marker", "PAC")]
        assert f.timeline_kinds == {
            "marker": 1,
            "score": 1,
            "pdf": 1,
            "audiowave": 1,
            "slider": 1,
            "spectrogram": 1,
        }


def test_scenario_6_the_corpus_goes_straight_to_tql_run(tmp_path):
    corpus_docs.write_doc(tmp_path / "a.tla", song("a", ["verse", "chorus", "verse"]))
    corpus_docs.write_doc(tmp_path / "b.tla", song("b", ["chorus", "verse"]))
    with opened(tmp_path) as corpus:
        result = tql.run(corpus, "verse THEN chorus IN form")
        assert [m.slots[0][0].label for m in result.matches] == ["verse"]
        assert result.generation == corpus.generation == 1


def test_an_empty_folder_gives_an_empty_index(tmp_path):
    with opened(tmp_path) as corpus:
        assert corpus.files() == []
        assert not corpus.open_report
        assert corpus.generation == 0
        assert tql.run(corpus, "verse IN form").matches == []


# --------------------------------------------------------------------------- #
# The path
# --------------------------------------------------------------------------- #
def test_a_file_raises_not_a_directory_and_a_tla_suggests_its_folder(tmp_path):
    path = corpus_docs.write_doc(tmp_path / "a.tla", song("a"))
    with pytest.raises(NotADirectoryError) as caught:
        opened(path)
    assert "is a file, not a folder" in str(caught.value)
    assert f"open {tmp_path}" in str(caught.value)
    other = tmp_path / "notes.txt"
    other.write_text("x")
    with pytest.raises(NotADirectoryError) as caught:
        opened(other)
    assert "open " not in str(caught.value).split("folder", 1)[1]


def test_a_missing_path_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError) as caught:
        opened(tmp_path / "nowhere")
    assert "no such folder" in str(caught.value)
    assert caught.value.filename == str(tmp_path / "nowhere")


def test_a_folder_that_cant_be_listed_raises_the_systems_error_naming_it(
    tmp_path, monkeypatch
):
    real = os.scandir

    def scandir(path="."):
        if Path(path) == tmp_path:
            raise PermissionError(13, "Permission denied")  # no file name
        return real(path)

    monkeypatch.setattr(os, "scandir", scandir)
    with pytest.raises(PermissionError) as caught:
        opened(tmp_path)
    assert caught.value.filename == str(tmp_path)
    assert "Permission denied" in str(caught.value)


def test_the_path_is_expanded_and_resolved(tmp_path, monkeypatch):
    corpus_docs.write_doc(tmp_path / "home" / "c" / "a.tla", song("a"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    with opened("~/c/../c") as corpus:
        assert corpus.path == (tmp_path / "home" / "c").resolve()
        assert [f.path for f in corpus.files()] == ["a.tla"]


def test_without_a_reader_it_says_none_is_there_yet(tmp_path):
    with pytest.raises(NotImplementedError, match="project-management#7"):
        open_corpus(tmp_path)


# --------------------------------------------------------------------------- #
# What it returns
# --------------------------------------------------------------------------- #
def test_the_dataclasses_are_frozen():
    for cls in (FileRow, TimelineRow, FileDetail, ComponentRow, ScanReport):
        assert dataclasses.is_dataclass(cls) and cls.__dataclass_params__.frozen


def test_files_and_file_give_the_rows_of_files(tmp_path):
    doc = dataclasses.replace(song("a"), fields={"composer": "Ana", "tags": ["x", "y"]})
    path = corpus_docs.write_doc(tmp_path / "sub" / "a.tla", doc)
    broken_at_line_12(tmp_path / "b.tla")
    with opened(tmp_path, rescan_before_reads=False) as corpus:
        assert isinstance(corpus, Corpus) and corpus.rescan_before_reads is False
        assert corpus.available is True
        b, a = corpus.files()  # by path
        assert (a.path, a.document_id, a.state, a.reason) == (
            "sub/a.tla",
            "a",
            "readable",
            None,
        )
        assert a.format_version == "1.0"
        assert a.fingerprint == corpus._scanner.records["sub/a.tla"].fingerprint
        assert a.fields == {"composer": ("Ana",), "tags": ("x", "y")}
        assert a.timeline_kinds == {"hierarchy": 1}
        assert (b.path, b.state, b.document_id, b.fingerprint) == (
            "b.tla",
            "unreadable",
            None,
            None,
        )
        assert corpus.file("sub/a.tla") == a
        assert corpus.file(path) == a  # as given
        assert corpus.file(os.path.join("sub", "a.tla")) == a
        assert corpus.file("missing.tla") is None
        assert corpus.file(tmp_path.parent / "elsewhere.tla") is None


def test_file_detail_gives_the_timelines_in_ordinal_order(tmp_path):
    corpus_docs.write_doc(tmp_path / "a.tla", corpus_docs.every_kind(document_id="a"))
    with opened(tmp_path) as corpus:
        (f,) = corpus.files()
        detail = corpus.file_detail(f.id)
        assert detail.file == f
        assert [t.ordinal for t in detail.timelines] == list(range(1, 9))
        form = detail.timelines[0]
        assert (form.uuid, form.kind, form.name, form.role, form.author) == (
            "t1",
            "hierarchy",
            "Form (A)",
            "form",
            "Ana",
        )
        assert form.fields == {"tags": ("draft", "done")}
        with pytest.raises(KeyError):
            corpus.file_detail(999)


def test_components_give_what_every_unit_has_and_what_its_kind_adds(tmp_path):
    ranges = corpus_docs.ranges(["solo"], [["solo", "S", 2, 8]], tid="r", ordinal=3)
    (unit,) = ranges.components
    coloured = dataclasses.replace(unit, attrs={**unit.attrs, "color": "#00FF00"})
    ranges = dataclasses.replace(ranges, components=(coloured,))
    doc = corpus_docs.every_kind(document_id="a")
    doc = dataclasses.replace(doc, timelines=(*doc.timelines, ranges))
    corpus_docs.write_doc(tmp_path / "a.tla", doc)
    with opened(tmp_path) as corpus:
        (f,) = corpus.files()
        detail = corpus.file_detail(f.id)
        tids = {t.uuid: t.id for t in detail.timelines}
        units = {u.uuid: u for u in corpus.components(f.id, tids.values())}
        top, child = units["t1:c1"], units["t1:c2"]
        assert top.properties == {
            "level": 2,
            "parent_id": None,
            "depth": 1,
            "color": "#ffc0cb",
        }
        assert child.properties == {"level": 1, "parent_id": top.id, "depth": 2}
        assert units["r:c1"].properties == {
            "row_id": "r:r1",
            "row": "solo",
            "row_folded": "solo",
            "color": "#00ff00",
        }
        assert units["t3:c1"].properties == {
            "row_id": "t3:r1",
            "row": "solo",
            "row_folded": "solo",
        }
        pac, hc = units["t2:c1"], units["t2:c2"]
        assert pac.properties == {"color": "#ff0000"} and hc.properties == {}
        assert (pac.start, pac.end) == (5, 5)
        beat = units["t5:c2"]
        assert (beat.kind, beat.label, beat.properties) == ("beat", "", {})
        assert beat.start == beat.end == 1
        chord = units["t4:c1"]
        assert "color" not in chord.properties
        assert chord.properties["quality"] == "major"
        assert chord.end == units["t4:c2"].start
        assert (top.timeline_id, top.kind, top.label) == (tids["t1"], "hierarchy", "A")
        # in time order, and only the timelines asked for
        listed = corpus.components(f.id, [tids["t2"], tids["t1"]])
        assert [u.start for u in listed] == sorted(u.start for u in listed)
        assert {u.timeline_id for u in listed} == {tids["t1"], tids["t2"]}
        assert corpus.components(f.id, []) == []


def test_the_index_reader_and_closing(tmp_path):
    corpus_docs.write_doc(tmp_path / "a.tla", song("a"))
    corpus = opened(tmp_path)
    with pytest.raises(RuntimeError):
        corpus.connection()
    with corpus.reading() as r:
        assert corpus.connection() is r.connection
        assert (r.generation, r.available) == (1, True)
        (key,) = r.connection.execute("SELECT id FROM files").fetchone()
    assert corpus.time_map(key) is None
    with corpus.reading():
        with pytest.raises(RuntimeError):
            corpus.close()
    with corpus:
        pass  # leaving closes it
    with pytest.raises(RuntimeError):
        corpus.files()
    corpus.close()  # a second close does nothing


def test_the_time_maps_come_from_time_map_of(tmp_path):
    import fake_timemap

    corpus_docs.write_doc(tmp_path / "a.tla", corpus_docs.every_kind(document_id="a"))
    with opened(tmp_path, time_map_of=fake_timemap.time_map_of) as corpus:
        (f,) = corpus.files()
        tmap = corpus.time_map(f.id)
        assert tmap is not None and tmap.timeline_id == "t5"
        with corpus.reading() as r:
            assert r.time_map(f.id) is tmap
            assert (
                r.connection.execute("SELECT count(*) FROM measures").fetchone()[0] == 3
            )
        assert corpus._scanner.records["a.tla"].time_map is tmap


def test_opening_writes_nothing_in_the_folder(tmp_path):
    corpus_docs.write_doc(tmp_path / "a.tla", song("a"))
    broken_at_line_12(tmp_path / "b.tla")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*")}
    with opened(tmp_path) as corpus:
        corpus.files()
    assert {p: p.read_bytes() for p in tmp_path.rglob("*")} == before


def test_it_closes_its_store_when_the_folder_cant_be_listed(tmp_path, monkeypatch):
    opened_stores = []
    real = scan.Scanner.__init__

    def init(self, root, store, *args, **kw):
        opened_stores.append(store)
        real(self, root, store, *args, **kw)

    monkeypatch.setattr(scan.Scanner, "__init__", init)
    monkeypatch.setattr(
        os, "scandir", lambda path=".": (_ for _ in ()).throw(PermissionError(13, "no"))
    )
    with pytest.raises(PermissionError):
        opened(tmp_path)
    (store,) = opened_stores
    with pytest.raises(RuntimeError):
        with store.reading():
            pass
