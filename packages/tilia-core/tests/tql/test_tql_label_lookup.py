"""Which timelines of a file hold a unit with a label is looked up once a run
for every file (compile.Catalog.label_timelines), starting from the index of
categories, and finds what a lookup of the file's alone finds."""

import copy
import re

import examples
import fixture_index
import pytest

from tilia_core import tql
from tilia_core.tql import compile as tql_compile
from tilia_core.tql import sqlfuncs, syntax
from tilia_core.tql.engine import _lane_units

FIXTURES = examples.load()["fixtures"]
NAMES = ["sonata", "pop", "harmony", "repeat", "recipe", "exposition"]
LOOKUP = "SELECT DISTINCT c.file_id, c.timeline_id FROM components c"
LABELS = [
    "verse",
    "verse OR chorus",
    "VERSE",
    "verse AND NOT chorus",
    "NOT verse",
    "NOT verse OR chorus",
    "NOT (verse OR chorus) AND NOT bridge",
    "bridge",
    "bridge.modern",
    "verse.a",
    "verse.b",
    "pac",
    "i:pac",
    "V",
    "V7",
    "I",
    "ii",
    "C",
    "NOT V",
    "V OR I",
    "V AND NOT I",
    "phrase AND NOT V",
    "nothing",
    '"verse"',
    "/^ver/",
    "verse OR /^cho/",
    "* AND NOT verse",
]


def _dotted() -> dict:
    """``pop`` with subtypes: ``verse.a`` and ``bridge.modern``."""
    fixture = copy.deepcopy(FIXTURES["pop"])
    fixture["name"] = "dotted"
    for tl in fixture["timelines"]:
        for unit in tl.get("units", []):
            if unit[0] == "verse":
                unit[0] = "verse.a"
            elif unit[0] == "bridge":
                unit[0] = "bridge.modern"
    return fixture


@pytest.fixture(scope="module")
def index():
    return fixture_index.build_index(*(FIXTURES[n] for n in NAMES), _dotted())


def _term(label: str) -> syntax.Term:
    ((unit, _),) = list(_lane_units(syntax.parse(f"{label} IN form")))
    assert unit.term is not None
    return unit.term


def _own_lookup(con, file_id, term: syntax.Term) -> frozenset:
    """A lookup of one file's alone, as a run made one before."""
    bld = tql_compile.SqlBuilder(None, False)
    bld.params.append(file_id)
    test = tql_compile.unit_test(syntax.Unit(term, [], 0), "c", bld)
    rows = con.execute(
        f"SELECT DISTINCT c.timeline_id FROM components c "
        f"WHERE c.file_id = ? AND ({test})",
        bld.params,
    )
    return frozenset(r[0] for r in rows)


@pytest.mark.parametrize("label", LABELS)
def test_the_lookup_of_every_file_finds_what_each_files_own_finds(index, label):
    con = index.connection()
    sqlfuncs.register(con, index)
    term = _term(label)
    by_file = tql_compile.Catalog(con).label_timelines(term)
    keys = [r[0] for r in con.execute("SELECT id FROM files ORDER BY id")]
    for key in keys:
        own = _own_lookup(con, key, term)
        alone = tql_compile.Catalog(con, key).label_timelines(term)
        if by_file is None:
            assert alone is None
            continue
        assert by_file.get(key, frozenset()) == own
        assert alone is not None and alone.get(key, frozenset()) == own


def test_the_lookups_find_something(index):
    con = index.connection()
    sqlfuncs.register(con, index)
    catalog = tql_compile.Catalog(con)
    for label in ("verse", "bridge.modern", "bridge", "V7", "V AND NOT I"):
        assert catalog.label_timelines(_term(label)), label


def test_a_label_without_a_word_is_left_to_each_file(index):
    con = index.connection()
    for label in ('"verse"', "/^ver/", "verse OR /^cho/", "* AND NOT verse"):
        assert tql_compile.Catalog(con).label_timelines(_term(label)) is None


def _statements(index, query):
    ran = []
    index.connection().set_trace_callback(ran.append)
    try:
        got = tql.run(index, query)
    finally:
        index.connection().set_trace_callback(None)
    return got, ran


def test_a_run_looks_up_a_label_once_for_every_file(index):
    got, ran = _statements(index, "nothing THEN verse THEN chorus IN form")
    assert got.matches == []  # so that the hints look up labels too
    lookups = [s for s in ran if LOOKUP in s and "categories WHERE" in s]
    assert len(lookups) == 3  # one per label: nothing, verse, chorus
    assert not [s for s in ran if "SELECT DISTINCT c.timeline_id FROM components" in s]


def test_the_lookup_starts_from_the_index_of_categories(index):
    _, ran = _statements(index, "nothing THEN verse IN form")
    lookups = [s for s in ran if LOOKUP in s and "categories WHERE" in s]
    assert lookups
    con = index.connection()
    for statement in lookups:
        plan = [r[-1] for r in con.execute("EXPLAIN QUERY PLAN " + statement)]
        assert any(
            re.search(r"USING (COVERING )?INDEX categories_by_category", p)
            for p in plan
        ), plan
        assert not any(re.fullmatch(r"SCAN c\b.*", p) for p in plan), plan
