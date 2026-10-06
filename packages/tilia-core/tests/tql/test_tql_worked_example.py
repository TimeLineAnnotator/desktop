"""The worked example's match table: the thirteen rows of plan §4.2, on the
``exposition`` fixture."""

from collections import Counter

import examples
import fixture_index
import pytest

from tilia_core import tql

DATA = examples.load()
ROWS = [e for e in DATA["examples"] if e.plan.startswith("§4.2 table")]

# rows that need a later part of the language
LATER: dict[int, str] = {}


def _unit(component, marked):
    text = f"{component.label}@{component.start:g}"
    return f"[{text}]" if marked else text


def _row(match, has_target):
    steps = []
    for n, slot in enumerate(match.slots):
        units = [
            _unit(c, has_target and match.is_target(n + 1, k))
            for k, c in enumerate(slot)
        ]
        if units:
            steps.append(", ".join(units))
    return " | ".join(steps)


def _params():
    out = []
    for e in ROWS:
        number = int(e.plan.rsplit(" ", 1)[1])
        marks = []
        if number in LATER:
            marks.append(pytest.mark.xfail(strict=True, reason=LATER[number]))
        out.append(pytest.param(e, id=f"row{number}", marks=marks))
    return out


def test_there_are_thirteen_rows():
    assert [e.plan for e in ROWS] == [f"§4.2 table, row {n}" for n in range(1, 14)]
    assert {e.fixture for e in ROWS} == {"exposition"}


@pytest.mark.parametrize("example", _params())
def test_row(example):
    index = fixture_index.build_index(DATA["fixtures"][example.fixture])
    result = tql.run(index, example.query)
    has_target = tql.parse(example.query).has_target
    assert Counter(_row(m, has_target) for m in result.matches) == Counter(example.rows)


def test_the_cadence_that_ends_st_is_the_pac():
    index = fixture_index.build_index(DATA["fixtures"]["exposition"])
    result = tql.run(index, "* IN cadences ENDS ST IN form")
    [row] = result.rows
    assert row["label"] == "PAC"
    assert (row["$1.label"], row["$2.label"]) == ("PAC", "ST")
    assert (row["$2.start"], row["$2.end"]) == (10, 22)
    assert row["$2.timeline"] == "Form (Caplin) · level 2"
    assert row["$1.timeline"] == "Cadences"


def test_the_children_of_st_are_not_the_children_of_the_exposition():
    index = fixture_index.build_index(DATA["fixtures"]["exposition"])
    assert tql.run(index, "ST[continuation{2}] IN form").matches
    assert not tql.run(index, "exposition[continuation] IN form").matches
    assert tql.run(index, "exposition[CONTAINS continuation] IN form").matches
