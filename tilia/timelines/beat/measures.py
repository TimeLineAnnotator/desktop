"""
A beat timeline's measures, read from the beats that start them.

Each beat that starts a measure carries `is_first_in_measure`, and the
measure's own data: a number set by hand (`measure_number_override`) and
whether that number is always shown. A measure's beats are the beats from its
first beat to the next one's, so no count is stored and nothing kept by
measure index can drift from the beats. `Measures` is the table built from
them; the timeline caches it until its beats change.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tilia.timelines.beat.components import Beat


@dataclass(frozen=True)
class Measures:
    # The index of the first beat of each measure.
    starts: list[int]
    counts: list[int]
    numbers: list[int]
    # Indices of measures whose number is always shown.
    always_shown: list[int]
    # The measure each beat is in, by beat index.
    measure_of_beat: list[int]

    @property
    def count(self) -> int:
        return len(self.starts)


def build_measures(beats: Sequence[Beat]) -> Measures:
    """
    The measures of `beats`, in time order. The first beat always starts a
    measure, whether or not it is marked. A measure without a number of its
    own is numbered one more than the measure before, and the first one 1.
    """
    starts: list[int] = []
    numbers: list[int] = []
    always_shown: list[int] = []
    measure_of_beat: list[int] = []
    for index, beat in enumerate(beats):
        if index == 0 or beat.is_first_in_measure:
            if beat.measure_number_override is not None:
                number = beat.measure_number_override
            else:
                number = numbers[-1] + 1 if numbers else 1
            if beat.measure_number_always_shown:
                always_shown.append(len(starts))
            starts.append(index)
            numbers.append(number)
        measure_of_beat.append(len(starts) - 1)

    ends = starts[1:] + [len(beats)] if starts else []
    counts = [end - start for start, end in zip(starts, ends, strict=True)]
    return Measures(starts, counts, numbers, always_shown, measure_of_beat)


def get_extension_from_beat_pattern(
    beat_pattern: list[int],
    amount: int,
    start_index: int = 0,
    beats_on_starting_measure: int = 0,
) -> list[int]:
    """
    The measure lengths that `amount` more beats make, following the pattern
    cyclically from `start_index`. With `beats_on_starting_measure`, the
    first entry tops up a measure that already has that many beats.
    """
    if amount == 0:
        return []

    if start_index < 0:
        raise ValueError(f"Start index must be a positive value. Got {start_index}")

    beat_pattern_cycle = itertools.cycle(beat_pattern)

    # iterate up to start index
    for _ in range(start_index):
        next(beat_pattern_cycle)

    if beats_on_starting_measure:
        beats = next(beat_pattern_cycle)
        if beats_on_starting_measure < beats:
            diff = beats - beats_on_starting_measure
            extension = [min(diff, amount)]
            remaining_beats = amount - diff
        else:
            # A measure may hold more beats than the beat pattern
            # prescribes for it, as "Set amount in measure" sets an
            # arbitrary amount. There is nothing left to fill in that
            # case, so the extension starts a new measure.
            extension = []
            remaining_beats = amount
    else:
        extension = []
        remaining_beats = amount

    if remaining_beats > 0:
        for beats in beat_pattern_cycle:
            if remaining_beats > beats:
                remaining_beats -= beats
                extension.append(beats)
            else:
                extension.append(remaining_beats)
                break

    return extension


def fit_legacy_lists(
    beat_count: int,
    pattern: list[int],
    beats_in_measure: list[int],
    measure_numbers: list[int],
) -> tuple[list[int], list[int]]:
    """
    Fits the lists by measure that files from before measures were marked on
    their beats store, `beats_in_measure` and `measure_numbers`, to
    `beat_count` beats, as TiLiA did when it loaded them: missing measures
    are made from the pattern and numbered on from the last, and surplus ones
    are dropped from the end.
    """
    counts = list(beats_in_measure)
    delta = beat_count - sum(counts)
    if delta > 0:
        counts = _extend_legacy_counts(counts, pattern, delta)
    elif delta < 0:
        counts = _reduce_legacy_counts(counts, -delta)

    numbers = list(measure_numbers[: len(counts)])
    while len(numbers) < len(counts):
        numbers.append(numbers[-1] + 1 if numbers else 1)
    return counts, numbers


def _extend_legacy_counts(
    counts: list[int], pattern: list[int], amount: int
) -> list[int]:
    if not counts:
        return get_extension_from_beat_pattern(pattern, amount)

    measure_count = len(counts)
    start_index = (measure_count % len(pattern) - 1) % measure_count
    beats_on_starting_measure = counts[-1]
    if start_index == -1 and beats_on_starting_measure == pattern[-1]:
        beats_on_starting_measure = 0
        start_index = 0
    extension = get_extension_from_beat_pattern(
        pattern,
        amount,
        start_index=start_index,
        beats_on_starting_measure=beats_on_starting_measure,
    )

    is_last_measure_complete = counts[-1] >= pattern[(measure_count % len(pattern)) - 1]
    if is_last_measure_complete:
        return counts + extension
    return counts[:-1] + [counts[-1] + extension[0]] + extension[1:]


def _reduce_legacy_counts(counts: list[int], amount: int) -> list[int]:
    counts = counts.copy()
    remaining_beats = amount
    for beats in reversed(counts.copy()):
        if beats < remaining_beats:
            counts.pop(-1)
            remaining_beats -= beats
        elif beats > remaining_beats:
            counts[-1] -= remaining_beats
            break
        else:
            counts.pop(-1)
            break
    return counts
