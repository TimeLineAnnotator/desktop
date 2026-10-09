"""Each measure's meter, from the beat units set on its beats, with desktop#621's rules."""

from __future__ import annotations

import logging
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
    validate_denominator,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _BeatUnit:
    """A beat unit as desktop#621's component holds it, with its beat's id as its id."""

    id: str
    denominator: int
    units: str
    assumed: bool

    @property
    def unit_values(self) -> list[Fraction]:
        return parse_units(self.units).units


def meters_of(rows: Sequence[RowIn]) -> list[MeasureMeter]:
    """
    The meter of every measure, from the beat units in effect: the loop of
    desktop#621's `BeatTimeline._compute_measure_meters`. The first unit set
    in a measure governs it and is carried forward; any other in that measure
    makes it conflicting. Until a unit is set, a measure of N taps is N/4,
    assumed. A unit that can't be read is ignored, as if absent.
    """
    default_units = parse_units(DEFAULT_UNITS).units

    meters = []
    governing: _BeatUnit | None = None
    for row in rows:
        beat_count = len(row.beat_ids)
        in_measure = [
            beat_unit
            for beat_id, unit in row.units
            if (beat_unit := _readable(beat_id, unit)) is not None
        ]
        if in_measure:
            governing = in_measure[0]

        if governing is None:
            denominator, units = DEFAULT_DENOMINATOR, default_units
        else:
            denominator, units = governing.denominator, governing.unit_values

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


def _readable(beat_id: str, unit: tla.BeatUnit) -> _BeatUnit | None:
    # desktop#621 refuses to create such a unit, and so drops it from a file
    # it loads: the unit before carries on.
    if (
        not isinstance(unit.units, str)
        or not parse_units(unit.units).is_valid
        or not validate_denominator(unit.denominator)
    ):
        logger.warning(
            "Beat %s: the beat unit %r over %r can't be read; ignored.",
            beat_id,
            unit.units,
            unit.denominator,
        )
        return None
    return _BeatUnit(
        id=beat_id,
        denominator=unit.denominator,
        units=unit.units,
        assumed=unit.assumed,
    )
