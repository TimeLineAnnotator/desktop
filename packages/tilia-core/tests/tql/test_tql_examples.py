"""The printed examples, run through ``tql.run``."""

from collections import Counter
from pathlib import Path

import examples
import fixture_index
import pytest

from tilia_core import tql

DATA = examples.load()
PENDING_FILE = Path(__file__).with_name("examples_pending.txt")


def _pending() -> dict[int, str]:
    out: dict[int, str] = {}
    for line in PENDING_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            n, _, reason = line.partition(":")
            out[int(n)] = reason.strip()
    return out


PENDING = _pending()


def _unit(component, marked: bool) -> str:
    text = f"{component.label}@{component.start:g}"
    return f"[{text}]" if marked else text


def _row(match: tql.Match, has_target: bool) -> str:
    steps = []
    for n, slot in enumerate(match.slots):
        units = [
            _unit(c, has_target and match.is_target(n + 1, k))
            for k, c in enumerate(slot)
        ]
        if units:
            steps.append(", ".join(units))
    return " | ".join(steps)


def _rows(result: tql.Result, has_target: bool) -> list[str]:
    """A query of only WHERE lists timelines by name; the rest by their units."""
    if result.grain == "timeline":
        return [r["timeline"] for r in result.rows]
    return [_row(m, has_target) for m in result.matches]


def _params():
    out = []
    for e in DATA["examples"]:
        marks = []
        if e.n in PENDING:
            marks.append(pytest.mark.xfail(strict=True, reason=PENDING[e.n]))
        out.append(pytest.param(e, id=str(e.n), marks=marks))
    return out


def test_pending_numbers_are_examples():
    numbers = {e.n for e in DATA["examples"]}
    assert set(PENDING) <= numbers


@pytest.mark.parametrize("example", _params())
def test_example(example):
    index = fixture_index.build_index(DATA["fixtures"][example.fixture])
    result = tql.run(index, example.query)
    has_target = tql.parse(example.query).has_target
    got = Counter(_rows(result, has_target))
    assert got == Counter(example.rows)
