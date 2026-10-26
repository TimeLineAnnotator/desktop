"""One document's index rows (research R12), and their equivalence with WP13's
fixture index, fixture by fixture (SC-003's preparation)."""

import dataclasses
import itertools
import sqlite3
import unicodedata

import corpus_docs
import examples
import fake_timemap
import fixture_index
import pytest
from grammars import GRAMMARS

from tilia_core import labels
from tilia_core.corpus import build
from tilia_core.corpus.schema import create_schema
from tilia_core.corpus.settings import NoSettings

FIXTURES = examples.load()["fixtures"]


class Settings(NoSettings):
    """Settings that set roles by timeline name and a label grammar."""

    def __init__(self, roles=None, grammar=None):
        self.roles = roles or {}
        self._grammar = grammar or labels.WholeLabel()

    def role(self, timeline, document):
        return self.roles.get(timeline.name)

    def grammar(self, timeline, document):
        return self._grammar


def counter():
    return itertools.count(1).__next__


def rows_of(document, settings=None, time_map=None):
    return build.rows(document, settings or NoSettings(), counter(), time_map)


def index_of(rows, path="doc.tla"):
    """A fresh index holding ``rows``."""
    con = sqlite3.connect(":memory:")
    create_schema(con)
    for table, found in rows.at(path, None).tables().items():
        if found:
            marks = ", ".join("?" for _ in found[0])
            con.executemany(f"INSERT INTO {table} VALUES ({marks})", found)
    return con


def by_uuid(rows, uuid):
    """The row of ``components`` of the unit whose own id is ``uuid``."""
    (row,) = [r for r in rows.components if r[3] == uuid]
    return row


# --------------------------------------------------------------------------- #
# Each kind's rows
# --------------------------------------------------------------------------- #
class TestKinds:
    doc = corpus_docs.every_kind()
    rows = rows_of(doc)

    def test_every_timeline_has_a_row(self):
        got = [(r[2], r[3], r[4], r[6]) for r in self.rows.timelines]
        assert got == [
            (tl.id, tl.kind, tl.name, tl.ordinal) for tl in self.doc.timelines
        ]
        assert {r[1] for r in self.rows.timelines} == {self.rows.file_id}

    def test_the_files_row(self):
        (row,) = self.rows.files
        assert row == (
            self.rows.file_id,
            None,
            "doc",
            corpus_docs.FORMAT_VERSION,
            "readable",
            None,
            None,
            60.0,
            "seconds",
            None,
            None,
        )
        (row,) = self.rows.at("a/doc.tla", "ab12").files
        assert (row[1], row[6]) == ("a/doc.tla", "ab12")

    def test_keys_come_from_the_callable_and_are_unique(self):
        keys = [self.rows.file_id]
        keys += [r[0] for r in self.rows.timelines] + [
            r[0] for r in self.rows.components
        ]
        assert sorted(keys) == list(range(1, len(keys) + 1))

    def test_hierarchy(self):
        a, small, b = (by_uuid(self.rows, f"t1:c{n}") for n in (1, 2, 3))
        assert a[4:10] == ("hierarchy", 0.0, 20.0, "A", "#ffc0cb", "")
        assert small[4:10] == ("hierarchy", 0.0, 10.0, "a", None, "")
        hier = {r[0]: r[1:] for r in self.rows.hierarchies}
        assert hier[a[0]] == (2, None, 1)
        assert hier[small[0]] == (1, a[0], 2)
        assert hier[b[0]] == (1, a[0], 2)
        cats = {(r[0], r[1], r[2]) for r in self.rows.categories}
        assert {(a[0], "a", None), (small[0], "a", None), (b[0], "b", None)} <= cats

    def test_marker(self):
        pac, hc = by_uuid(self.rows, "t2:c1"), by_uuid(self.rows, "t2:c2")
        assert pac[4:9] == ("marker", 5.0, 5.0, "PAC", "#ff0000")
        assert hc[4:9] == ("marker", 15.0, 15.0, "HC", None)
        cats = {(r[0], r[1]) for r in self.rows.categories}
        assert {(pac[0], "pac"), (hc[0], "hc")} <= cats

    def test_range(self):
        s, t = by_uuid(self.rows, "t3:c1"), by_uuid(self.rows, "t3:c2")
        assert s[4:8] == ("range", 2.0, 8.0, "S")
        ranges = {r[0]: r[1:] for r in self.rows.ranges}
        assert ranges[s[0]] == ("t3:r1", "solo", "solo")
        assert ranges[t[0]] == ("t3:r2", "tutti", "tutti")

    def test_harmony(self):
        c_major, g_minor = by_uuid(self.rows, "t4:k1"), by_uuid(self.rows, "t4:k2")
        # keys and chords last until the next of their kind, the last to the end
        assert c_major[4:8] == ("key", 0.0, 10.0, "C")
        assert g_minor[4:8] == ("key", 10.0, 60.0, "g")
        keys = {r[0]: r[1:] for r in self.rows.keys}
        assert keys[c_major[0]] == (0, 0, "major", "C", "C")
        assert keys[g_minor[0]] == (4, 0, "minor", "G", "g")
        one, five, five_minor = (by_uuid(self.rows, f"t4:c{n}") for n in (1, 2, 3))
        assert [r[4:8] for r in (one, five, five_minor)] == [
            ("chord", 0.0, 5.0, "I"),
            ("chord", 5.0, 10.0, "V65"),
            ("chord", 10.0, 60.0, "i"),
        ]
        chords = {r[0]: r[1:] for r in self.rows.chords}
        assert chords[five[0]][:7] == (4, 0, "dominant-seventh", 1, 0, None, c_major[0])
        assert chords[five_minor[0]][6] == g_minor[0]
        # no categories for chords and keys
        harmony = {r[0] for r in self.rows.components if r[4] in ("chord", "key")}
        assert not harmony & {r[0] for r in self.rows.categories}

    def test_beat(self):
        beats = [r for r in self.rows.components if r[4] == "beat"]
        assert [r[5] for r in beats] == [float(t) for t in range(12)]
        assert all(r[5] == r[6] and r[7] == "" for r in beats)
        # without a time map: no measures, no positions
        assert self.rows.measures == [] and self.rows.positions == []

    @pytest.mark.parametrize("kind", ["score", "pdf", "spectrogram"])
    def test_kinds_not_indexed_give_only_their_timeline_row(self, kind):
        (tl,) = [r for r in self.rows.timelines if r[3] == kind]
        assert not [r for r in self.rows.components if r[2] == tl[0]]
        assert not [r for r in self.rows.fields if r[1] == tl[0]]

    def test_a_document_of_only_unknown_kinds(self):
        doc = corpus_docs.document(
            corpus_docs.unindexed("score", tid="s", ordinal=1),
            corpus_docs.unindexed("audiowave", tid="a", ordinal=2),
            corpus_docs.unindexed("slider", tid="l", ordinal=3),
        )
        rows = rows_of(doc)
        assert [r[3] for r in rows.timelines] == ["score", "audiowave", "slider"]
        for table, found in rows.tables().items():
            if table not in ("files", "timelines"):
                assert found == [], table

    def test_the_rows_insert_into_the_schema(self):
        con = index_of(self.rows)
        assert con.execute("SELECT COUNT(*) FROM components").fetchone()[0] == len(
            self.rows.components
        )


# --------------------------------------------------------------------------- #
# Fields
# --------------------------------------------------------------------------- #
class TestFields:
    def test_a_list_field_is_one_row_per_item(self):
        rows = rows_of(corpus_docs.every_kind())
        file_tags = [r for r in rows.fields if r[0] == "file" and r[2] == "tags"]
        assert file_tags == [("file", rows.file_id, "tags", "test")]
        tl = rows.timelines[0][0]
        assert [r for r in rows.fields if r[1] == tl] == [
            ("timeline", tl, "tags", "draft"),
            ("timeline", tl, "tags", "done"),
        ]

    def test_role_and_author_are_columns_not_fields(self):
        rows = rows_of(corpus_docs.every_kind())
        assert rows.timelines[0][7:9] == ("form", "Ana")
        assert not [r for r in rows.fields if r[2] in ("role", "author")]

    def test_field_names_and_component_fields(self):
        tl = corpus_docs.markers([["PAC", 5]], tid="t1", ordinal=1)
        comp = dataclasses.replace(
            tl.components[0], fields={"Generated By": "tool", "tags": ["a", "b"]}
        )
        doc = corpus_docs.document(
            dataclasses.replace(tl, components=(comp,)), fields={"Opus No": 3}
        )
        rows = rows_of(doc)
        key = rows.components[0][0]
        assert sorted(rows.fields) == sorted(
            [
                ("component", key, "generated_by", "tool"),
                ("component", key, "tags", "a"),
                ("component", key, "tags", "b"),
                ("file", rows.file_id, "opus_no", "3"),
            ]
        )


# --------------------------------------------------------------------------- #
# Text in NFC (FR-045)
# --------------------------------------------------------------------------- #
def nfd(text):
    return unicodedata.normalize("NFD", text)


def test_text_written_in_nfd_is_stored_in_nfc():
    tl = corpus_docs.ranges(
        [nfd("Stimme ä")],
        [[nfd("Stimme ä"), nfd("Schluß é"), 0, 4]],
        tid="t1",
        name=nfd("Ébauche"),
        ordinal=1,
        fields={"vocabulary": nfd("Lied ö")},
    )
    comp = dataclasses.replace(
        tl.components[0],
        attrs=dict(tl.components[0].attrs, comments=nfd("à revoir")),
    )
    doc = corpus_docs.document(
        dataclasses.replace(tl, components=(comp,)), fields={"title": nfd("Größe ü")}
    )
    assert nfd("Schluß é") != "Schluß é"  # the test text has a decomposed form
    rows = rows_of(doc)
    (timeline,) = rows.timelines
    assert timeline[4:6] == ("Ébauche", "ébauche")
    (component,) = rows.components
    assert (component[7], component[9]) == ("Schluß é", "à revoir")
    (rng,) = rows.ranges
    assert rng[2:] == ("Stimme ä", "stimme ä")
    assert {r[3] for r in rows.fields} == {"Lied ö", "Größe ü"}
    assert [r[1] for r in rows.categories] == [labels.fold("Schluß é")]


def test_custom_text_is_stored_in_nfc():
    tl = corpus_docs.harmony([], [[0, "C", "major"]], tid="t1", ordinal=1)
    comp = dataclasses.replace(
        tl.components[0], attrs=dict(tl.components[0].attrs, custom_text=nfd("N.C. é"))
    )
    rows = rows_of(corpus_docs.document(dataclasses.replace(tl, components=(comp,))))
    assert rows.chords[0][6] == "N.C. é"


# --------------------------------------------------------------------------- #
# Roles and the time map
# --------------------------------------------------------------------------- #
def beats_document(role=None):
    beats = corpus_docs.beats(0, 1, 4, [1, 2], tid="b1", ordinal=1)
    other = corpus_docs.beats(0, 2, 2, [1, 2], tid="b2", name="Slow", ordinal=2)
    if role:
        other = dataclasses.replace(other, fields={"role": role})
    marks = corpus_docs.markers([["x", 4.5]], tid="m", ordinal=3)
    return corpus_docs.document(beats, other, marks, media_length=8.0)


def test_a_role_from_the_settings_wins_over_the_files():
    doc = corpus_docs.every_kind()
    rows = rows_of(doc, Settings(roles={"Form (A)": "melody"}))
    assert rows.timelines[0][7] == "melody"
    assert rows_of(doc).timelines[0][7] == "form"  # the file's own, without one
    assert (
        build.roles(doc, Settings(roles={"Cadences": "cadences"}))["t2"] == "cadences"
    )


def test_time_map_guessed_by_role():
    doc = beats_document(role="time_map")
    settings = NoSettings()
    tmap = fake_timemap.time_map_of(doc, build.roles(doc, settings))
    assert (tmap.timeline_id, tmap.guessed) == ("b2", False)
    rows = build.rows(doc, settings, counter(), tmap)
    slow = [r[0] for r in rows.timelines if r[2] == "b2"][0]
    assert rows.files[0][9:] == (slow, 0)


def test_time_map_guessed_by_fallback():
    doc = beats_document()
    tmap = fake_timemap.time_map_of(doc, build.roles(doc, NoSettings()))
    assert (tmap.timeline_id, tmap.guessed) == ("b1", True)
    rows = build.rows(doc, NoSettings(), counter(), tmap)
    first = [r[0] for r in rows.timelines if r[2] == "b1"][0]
    assert rows.files[0][9:] == (first, 1)


def test_a_role_the_settings_set_makes_the_time_map():
    doc = beats_document()
    roles = build.roles(doc, Settings(roles={"Slow": "time_map"}))
    assert fake_timemap.time_map_of(doc, roles).timeline_id == "b2"


def test_no_time_map_leaves_both_null():
    doc = beats_document()
    rows = rows_of(doc)
    assert rows.files[0][9:] == (None, None)
    assert rows.measures == [] and rows.positions == []
    assert (
        fake_timemap.time_map_of(corpus_docs.every_kind(document_id="x"), {})
        is not None
    )
    no_beats = corpus_docs.document(corpus_docs.markers([["x", 1]], tid="m", ordinal=1))
    assert fake_timemap.time_map_of(no_beats, {}) is None


def test_with_a_time_map_measures_and_positions():
    doc = beats_document()
    tmap = fake_timemap.time_map_of(doc, {})
    rows = build.rows(doc, NoSettings(), counter(), tmap)
    assert [r[1:] for r in rows.measures] == [
        (1, 1, "1", 0.0, 4.0, 4, 1),
        (2, 2, "2", 4.0, 8.0, 4, 1),
    ]
    (x,) = [r for r in rows.components if r[3] == "m:c1"]
    positions = {r[0]: r[1:] for r in rows.positions}
    assert positions[x[0]] == (2, 2, 1.5, 1, 2, "2", 4, 0)
    # every unit on the map has a row, the beats of both timelines too
    assert len(rows.positions) == len(rows.components)


def test_a_unit_off_the_map_has_no_position():
    doc = beats_document()
    tl = corpus_docs.markers([["early", -1], ["late", 9]], tid="m2", ordinal=4)
    doc = dataclasses.replace(doc, timelines=(*doc.timelines, tl))
    rows = build.rows(doc, NoSettings(), counter(), fake_timemap.time_map_of(doc, {}))
    off = {r[0] for r in rows.components if r[3].startswith("m2:")}
    assert not off & {r[0] for r in rows.positions}


# --------------------------------------------------------------------------- #
# Equivalence with WP13's fixture index
# --------------------------------------------------------------------------- #
# Each table with its keys written as the files' own ids. files.format_version
# and files.time_map_guessed are left out: the fixture index stores neither.
DUMP = {
    "files": "SELECT document_id, path, state, reason, fingerprint, media_length, "
    "time_unit, (SELECT uuid FROM timelines t WHERE t.id = f.time_map) FROM files f",
    "timelines": "SELECT f.document_id, t.uuid, t.kind, t.name, t.name_folded, "
    "t.ordinal, t.role, t.author FROM timelines t JOIN files f ON f.id = t.file_id",
    "components": 'SELECT f.document_id, t.uuid, c.uuid, c.kind, c.start, c."end", '
    "c.label, c.color, c.comments FROM components c "
    "JOIN files f ON f.id = c.file_id JOIN timelines t ON t.id = c.timeline_id",
    "hierarchies": "SELECT c.uuid, h.level, p.uuid, h.depth FROM hierarchies h "
    "JOIN components c ON c.id = h.component_id "
    "LEFT JOIN components p ON p.id = h.parent_id",
    "ranges": "SELECT c.uuid, r.row_id, r.row, r.row_folded FROM ranges r "
    "JOIN components c ON c.id = r.component_id",
    "chords": "SELECT c.uuid, x.step, x.accidental, x.quality, x.inversion, "
    "x.applied_to, x.custom_text, k.uuid, x.root, x.roman, x.symbol, x.key "
    "FROM chords x JOIN components c ON c.id = x.component_id "
    "LEFT JOIN components k ON k.id = x.key_id",
    "keys": "SELECT c.uuid, k.step, k.accidental, k.mode, k.tonic, k.key FROM keys k "
    "JOIN components c ON c.id = k.component_id",
    "categories": "SELECT c.uuid, x.category, x.supertype FROM categories x "
    "JOIN components c ON c.id = x.component_id",
    "positions": "SELECT c.uuid, p.bar, p.end_bar, p.beat, p.pass, p.bar_count, "
    "p.bar_label, p.bar_beat_count, p.downbeat FROM positions p "
    "JOIN components c ON c.id = p.component_id",
    "measures": 'SELECT f.document_id, m.count, m.number, m.label, m.start, m."end", '
    "m.beats, m.pass FROM measures m JOIN files f ON f.id = m.file_id",
    "fields": "SELECT x.scope, CASE x.scope "
    "WHEN 'file' THEN (SELECT document_id FROM files WHERE id = x.owner_id) "
    "WHEN 'timeline' THEN (SELECT uuid FROM timelines WHERE id = x.owner_id) "
    "ELSE (SELECT uuid FROM components WHERE id = x.owner_id) END, x.name, x.value "
    "FROM fields x",
}


def dump(con):
    def key(row):
        return [(v is None, "" if v is None else str(v)) for v in row]

    return {
        table: sorted(con.execute(sql).fetchall(), key=key)
        for table, sql in DUMP.items()
    }


def built_from_document(fixture):
    doc = corpus_docs.document_from_fixture(fixture)
    grammar = GRAMMARS[fixture["grammar"]] if "grammar" in fixture else None
    settings = Settings(grammar=grammar)
    tmap = fake_timemap.time_map_of(doc, build.roles(doc, settings))
    rows = build.rows(doc, settings, counter(), tmap)
    return index_of(rows, path=f"{doc.document_id}.tla")


def test_every_table_is_dumped():
    con = sqlite3.connect(":memory:")
    create_schema(con)
    tables = {
        r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert set(DUMP) == tables


@pytest.mark.parametrize("name", FIXTURES)
def test_the_rows_equal_the_fixture_indexs_tables(name):
    fixture = FIXTURES[name]
    got = dump(built_from_document(fixture))
    want = dump(fixture_index.build_index(fixture).connection())
    for table in DUMP:
        assert got[table] == want[table], (name, table)
    assert got["components"], name


# --------------------------------------------------------------------------- #
# What the fixtures don't cover
# --------------------------------------------------------------------------- #
def test_an_unindexed_timelines_fields_are_not_stored():
    pdf = dataclasses.replace(
        corpus_docs.unindexed("pdf", tid="p", ordinal=1), fields={"tags": ["scan"]}
    )
    rows = rows_of(corpus_docs.document(pdf))
    assert rows.fields == []


def test_chords_at_one_time_are_spanned_in_lane_order_not_file_order():
    # the file lists vii° before I at 0; by label, I comes first, so I ends
    # where it starts and vii° lasts until the next chord (lanes.lane_order)
    tl = corpus_docs.harmony(
        [[0, "C", "major"]],
        [[0, "B", "diminished"], [0, "C", "major"], [4, "G", "major"]],
        tid="h",
        ordinal=1,
    )
    rows = rows_of(corpus_docs.document(tl, media_length=8.0))
    spans = {r[7]: (r[5], r[6]) for r in rows.components if r[4] == "chord"}
    assert spans == {"I": (0.0, 0.0), "vii°": (0.0, 4.0), "V": (4.0, 8.0)}


def test_a_subtype_has_its_supertype_under_a_grammar_with_subtypes():
    tl = corpus_docs.hierarchy(
        [["bridge.modern", 1, 0, 10], ["verse", 1, 10, 20]], tid="f", ordinal=1
    )
    doc = corpus_docs.document(tl)
    rows = rows_of(doc, Settings(grammar=GRAMMARS["de Clercq"]))
    assert sorted(r[1:] for r in rows.categories) == [
        ("bridge.modern", "bridge"),
        ("verse", None),
    ]
    # without a grammar a dot is part of the label
    assert sorted(r[1:] for r in rows_of(doc).categories) == [
        ("bridge.modern", None),
        ("verse", None),
    ]
