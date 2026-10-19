"""Each measure's meter, from the beat units set on its beats.

The rules are those of desktop#621 (beat units and time signatures): its
`BeatTimeline._compute_measure_meters`, moved, with `units.py` beside it.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction

from tilia_core import tla
from tilia_core.timemap._rows import RowIn
from tilia_core.timemap.units import (
    DEFAULT_DENOMINATOR,
    DEFAULT_UNITS,
    MeasureMeter,
    fit_units,
    is_fit_ambiguous,
    parse_units,
)


@dataclass(frozen=True)
class _BeatUnit:
    """A beat unit as desktop#621's component holds it, with its beat's id as its id.

    Its units are parsed when it is read, not again for each measure it governs.
    """

    id: str | None  # None for a unit the core supplies at a movement's start
    denominator: int
    unit_values: tuple[Fraction, ...]
    assumed: bool


def meters_of(rows: Sequence[RowIn]) -> list[MeasureMeter]:
    """
    The meter of every measure, from the beat units in effect: the loop of
    desktop#621's `BeatTimeline._compute_measure_meters`. The first unit set
    in a measure governs it and is carried forward; any other in that measure
    makes it conflicting. `rows_of` has already left out the units that can't
    be read, so the unit before such a unit carries on.

    Every movement starts with a unit: the timeline's first measure, and
    each measure marked `restart`. Where a movement's first measure has none,
    the core supplies one, assumed, with no `beat_unit_id`, since no unit
    sits on those beats (`_supplied`). A movement's first measure always
    starts a unit, and no unit reaches back across a restart. Only here does
    this differ from #621's loop, which never meets such a timeline: #621's
    loader keeps a unit in the first measure (`_ensure_first_beat_unit`),
    copied from the first unit or the default, and #621 has no restarts.
    """
    meters = []
    governing: _BeatUnit | None = None
    for movement in _movements(rows):
        units_set = [[_parsed(*unit) for unit in row.units] for row in movement]
        first = next((unit for in_measure in units_set for unit in in_measure), None)
        governing = _supplied(first or governing)
        for index, (row, in_measure) in enumerate(
            zip(movement, units_set, strict=True)
        ):
            if in_measure:
                governing = in_measure[0]
            beat_count = len(row.beat_ids)
            units = list(governing.unit_values)
            meters.append(
                MeasureMeter(
                    denominator=governing.denominator,
                    units=tuple(units),
                    beat_values=tuple(fit_units(units, beat_count)),
                    beat_unit_id=governing.id,
                    starts_here=bool(in_measure) or index == 0,
                    is_ambiguous=is_fit_ambiguous(units, beat_count),
                    is_conflicting=len(in_measure) > 1,
                    is_assumed=governing.assumed,
                )
            )
    return meters


def _movements(rows: Sequence[RowIn]) -> Iterator[list[RowIn]]:
    """The rows by movement: one starts at the first row and at each restart."""
    movement: list[RowIn] = []
    for row in rows:
        if row.restart and movement:
            yield movement
            movement = []
        movement.append(row)
    if movement:
        yield movement


def _supplied(unit: _BeatUnit | None) -> _BeatUnit:
    """
    The unit the core supplies where a movement's first measure has none: a
    copy of `unit` (the movement's first, else the one in force before it),
    else the default. Assumed, since nobody set it there, and with no id,
    since no beat carries it.
    """
    if unit is None:
        return _DEFAULT
    return replace(unit, id=None, assumed=True)


def _parsed(beat_id: str, unit: tla.BeatUnit) -> _BeatUnit:
    return _BeatUnit(
        id=beat_id,
        denominator=unit.denominator,
        unit_values=tuple(parse_units(unit.units).units),
        assumed=unit.assumed,
    )


_DEFAULT = _BeatUnit(
    id=None,
    denominator=DEFAULT_DENOMINATOR,
    unit_values=tuple(parse_units(DEFAULT_UNITS).units),
    assumed=True,
)
