"""The package's public surface: the names its contract gives, their
docstrings, and the example in the package's README."""

import doctest
import inspect
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

import tilia_core.timemap as timemap
from docs import beat_timeline, document
from tilia_core.timemap import units

README = Path(__file__).parents[2] / "README.md"

# Every name of TimeLineAnnotator/project-management's
# specs/wp09-measure-table/contracts/python-api.md.
CONTRACT = [
    "DEFAULT_DENOMINATOR",
    "DEFAULT_UNITS",
    "MAX_DENOMINATOR",
    "MAX_UNIT_LENGTH",
    "BarRef",
    "Change",
    "FrozenMetadata",
    "MeasureMeter",
    "MeasureRow",
    "Meter",
    "Plan",
    "PlanOutOfDate",
    "Positions",
    "RowIn",
    "TimeMap",
    "TimeMapFound",
    "TimeSignature",
    "UnitsParseResult",
    "apply_plan",
    "find_time_map",
    "fit_units",
    "format_time_signature",
    "format_units",
    "is_fit_ambiguous",
    "measure_rows",
    "meters_of",
    "parse_units",
    "plan_time_signatures",
    "rows_of",
    "table_problem",
    "time_map_for",
    "time_map_of",
    "validate_denominator",
]


def test_timemap_all_holds_every_name_of_the_contract():
    assert sorted(timemap.__all__) == sorted(CONTRACT)


def test_timemap_star_import_gives_every_name():
    names = {}
    exec("from tilia_core.timemap import *", names)
    assert set(CONTRACT) <= set(names)


def test_timemap_meter_is_the_measure_meter():
    assert timemap.Meter is units.MeasureMeter


def test_timemap_meters_of_takes_what_rows_of_gives():
    timeline = beat_timeline(
        [
            {
                "time": 0.0,
                "measure": {},
                "beat_unit": {"denominator": 8, "units": "3"},
            },
            {"time": 1.0},
        ]
    )
    (meter,) = timemap.meters_of(timemap.rows_of(timeline))
    assert meter.time_signature == (6, 8)


def _public_functions():
    """Every function the package exports, and each exported class with what
    it defines: its methods, properties and class methods."""
    for name in timemap.__all__:
        value = getattr(timemap, name)
        if not inspect.isclass(value):
            if callable(value):
                yield name, value
            continue
        yield name, value
        for attribute, member in vars(value).items():
            if attribute.startswith("_"):
                continue
            if isinstance(member, property):
                yield f"{name}.{attribute}", member.fget
            elif isinstance(member, classmethod):
                yield f"{name}.{attribute}", member.__func__
            elif callable(member):
                yield f"{name}.{attribute}", member


PUBLIC_FUNCTIONS = [pytest.param(f, id=name) for name, f in _public_functions()]


def _written_docstring(value):
    doc = value.__doc__
    # A dataclass without a docstring gets its signature as one.
    if inspect.isclass(value) and doc and doc.startswith(f"{value.__name__}("):
        return None
    return doc


@pytest.mark.parametrize("function", PUBLIC_FUNCTIONS)
def test_timemap_public_function_has_a_docstring(function):
    assert _written_docstring(function)


def test_timemap_the_docstring_test_sees_a_dataclass_without_one():
    # Without this, the test above would pass whatever a dataclass has.
    @dataclass
    class Bare:
        value: int

    assert _written_docstring(Bare) is None


def _bars_and_beats_example() -> str:
    """The README section's code, as the doctest parser needs it: a closing
    fence right after an expected result would be read as part of that result."""
    text = README.read_text(encoding="utf-8")
    _, found, rest = text.partition("## Bars and beats\n")
    assert found, "the README has no section 'Bars and beats'"
    section = rest.partition("\n## ")[0]
    (example,) = re.findall(r"```pycon\n(.*?)```", section, re.DOTALL)
    return example


def _repeat_piece():
    """The document the example measures: a beat every second from 0, three to
    a bar, with bars 1 and 2 played twice."""
    marks = {0: {"number": 1}, 3: {"number": 2}, 6: {"number": 1}, 9: {"number": 2}}
    timeline = beat_timeline(
        [{"time": float(t), "measure": marks.get(t)} for t in range(12)],
        role="time_map",
    )
    return document(timeline, media_length=15.0)


def test_timemap_the_readme_example_runs():
    example = doctest.DocTestParser().get_doctest(
        _bars_and_beats_example(),
        {"document": _repeat_piece()},
        "Bars and beats",
        str(README),
        0,
    )
    assert any("time_map_of" in e.source for e in example.examples)
    assert any(".positions(" in e.source for e in example.examples)

    report = []
    runner = doctest.DocTestRunner(verbose=False)
    results = runner.run(example, out=report.append)

    assert results.failed == 0, "".join(report)
    assert results.attempted == len(example.examples) > 0
