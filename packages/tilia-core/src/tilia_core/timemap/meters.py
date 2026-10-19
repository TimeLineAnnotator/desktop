"""Each measure's meter, from the beat units set on its beats.

The rules are those of desktop#621 (beat units and time signatures): its
`BeatTimeline._compute_measure_meters`, moved, with `units.py` beside it.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
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
    sits on those beats (`_opening`). A movement's first measure always
    starts a unit, and no unit reaches back across a restart. Only here does
    this differ from #621's loop, which never meets such a timeline: #621's
    loader keeps a unit in the first measure (`_ensure_first_beat_unit`),
    copied from the first unit or the default, and #621 has no restarts.
    """
    meters = []
    governing: _BeatUnit | None = None
    for index, row in enumerate(rows):
        beat_count = len(row.beat_ids)
        in_measure = [_parsed(beat_id, unit) for beat_id, unit in row.units]
        starts_movement = index == 0 or row.restart
        if in_measure:
            governing = in_measure[0]
        elif starts_movement or governing is None:
            governing = _opening(rows, index, governing)

        denominator, units = governing.denominator, list(governing.unit_values)

        meters.append(
            MeasureMeter(
                denominator=denominator,
                units=tuple(units),
                beat_values=tuple(fit_units(units, beat_count)),
                beat_unit_id=governing.id,
                starts_here=bool(in_measure) or starts_movement,
                is_ambiguous=is_fit_ambiguous(units, beat_count),
                is_conflicting=len(in_measure) > 1,
                is_assumed=governing.assumed,
            )
        )
    return meters


def _opening(rows: Sequence[RowIn], start: int, before: _BeatUnit | None) -> _BeatUnit:
    """
    The unit the core supplies at the start of the movement that begins at
    `start`, whose first measure has none: a copy of the movement's first
    unit, else of the unit in force `before` it, else the default. Assumed,
    since nobody set it there, and with no id, since no beat carries it.
    """
    first = next((unit for row in _movement(rows, start) for unit in row.units), None)
    if first is not None:
        source = _parsed(*first)
        denominator, values = source.denominator, source.unit_values
    elif before is not None:
        denominator, values = before.denominator, before.unit_values
    else:
        denominator = DEFAULT_DENOMINATOR
        values = tuple(parse_units(DEFAULT_UNITS).units)
    return _BeatUnit(id=None, denominator=denominator, unit_values=values, assumed=True)


def _movement(rows: Sequence[RowIn], start: int) -> Iterator[RowIn]:
    """The rows from `start` up to the next restart."""
    yield rows[start]
    for row in rows[start + 1 :]:
        if row.restart:
            return
        yield row


def _parsed(beat_id: str, unit: tla.BeatUnit) -> _BeatUnit:
    return _BeatUnit(
        id=beat_id,
        denominator=unit.denominator,
        unit_values=tuple(parse_units(unit.units).units),
        assumed=unit.assumed,
    )
