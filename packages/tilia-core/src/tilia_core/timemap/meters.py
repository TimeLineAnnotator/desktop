"""Each measure's meter, from the beat units set on its beats.

The rules are those of desktop#621 (beat units and time signatures): its
`BeatTimeline._compute_measure_meters`, moved, with `units.py` beside it.
"""

from __future__ import annotations

from collections.abc import Sequence
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

    Its units are parsed once for each call of `meters_of`.
    """

    id: str
    denominator: int
    unit_values: tuple[Fraction, ...]
    assumed: bool


def meters_of(rows: Sequence[RowIn]) -> list[MeasureMeter]:
    """
    The meter of every measure, from the beat units in effect: the loop of
    desktop#621's `BeatTimeline._compute_measure_meters`. The first unit set
    in a measure governs it and is carried forward; any other in that measure
    makes it conflicting. Until a unit is set, a measure of N taps is N/4,
    assumed. `rows_of` has already left out the units that can't be read, so
    the unit before such a unit carries on.
    """
    default_units = parse_units(DEFAULT_UNITS).units

    meters = []
    governing: _BeatUnit | None = None
    for row in rows:
        beat_count = len(row.beat_ids)
        in_measure = [_parsed(beat_id, unit) for beat_id, unit in row.units]
        if in_measure:
            governing = in_measure[0]

        if governing is None:
            denominator, units = DEFAULT_DENOMINATOR, list(default_units)
        else:
            denominator, units = governing.denominator, list(governing.unit_values)

        meters.append(
            MeasureMeter(
                denominator=denominator,
                units=units,
                beat_values=fit_units(units, beat_count),
                beat_unit_id=governing.id if governing else None,
                starts_here=bool(in_measure),
                is_ambiguous=is_fit_ambiguous(units, beat_count),
                is_conflicting=len(in_measure) > 1,
                is_assumed=governing is None or governing.assumed,
            )
        )
    return meters


def _parsed(beat_id: str, unit: tla.BeatUnit) -> _BeatUnit:
    return _BeatUnit(
        id=beat_id,
        denominator=unit.denominator,
        unit_values=tuple(parse_units(unit.units).units),
        assumed=unit.assumed,
    )
