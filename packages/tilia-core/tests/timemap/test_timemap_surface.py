"""The package's public surface: the names its contract gives, and their docstrings."""

import inspect
from dataclasses import dataclass

import pytest

import tilia_core.timemap as timemap
from docs import beat_timeline
from tilia_core.timemap import units

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
