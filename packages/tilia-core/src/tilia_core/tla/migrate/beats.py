"""Beat timelines in old files: their measures, marked on their downbeats.

TiLiA 0.x keeps a beat timeline's measures in lists by measure,
`beats_in_measure`, `measure_numbers` and `measures_to_force_display`, and
fits them to the beats it has whenever it opens a file
(`BeatTimeline.recalculate_measures`): missing measures are made from the beat
pattern and numbered on from the last, and surplus ones come off the end. The
fitting is ported here, as pure functions on lists, from TiLiA 0.7.1's
`tilia/timelines/beat/timeline.py`, since the core can't import the app.

The prototype's `scripts/ql_timemap.py` (tla-corpus-ui) documents the same
rules, with the lines of TiLiA 0.6.3 they follow. They differ in one case: a
last measure that holds more beats than its pattern entry, in a timeline with
beats after it. TiLiA 0.6.3 to 0.7.0 can't open such a timeline, and the
prototype gives it no time map; TiLiA 0.7.1 and later start a new measure
with the beats after it, and so does this module
(TimeLineAnnotator/project-management#360).

Then, as contracts/migration.md's *Beat timelines* says, each measure's first
beat gets a `measure` mark: its `number` on the first measure, and where it
isn't the previous measure's plus one, and `force_display` where TiLiA always
shows it. desktop#621's beat units, components of their own that name their
beat, move onto that beat; with none, the first beat gets the default,
assumed. The timeline's `measure_source` is "unknown", since an old file
doesn't say whether its beats were tapped or imported (Q9).
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from tilia_core.labels import nfc
from tilia_core.tla.errors import printable
from tilia_core.tla.layout import TIMELINE_SHAPES, pointer_to
from tilia_core.tla.model import (
    ReadWarning,
    measures_of,
    timeline_kind_from_file,
)

# The report's count of measures with more than one beat unit.
TWO_BEAT_UNITS = "measures_with_two_beat_units"
# The lists by measure, which marks on the beats replace.
_LISTS = ("beats_in_measure", "measure_numbers", "measures_to_force_display")
_UNIT = "BEAT_UNIT"  # desktop#621's beat units, in the files it writes


@dataclass
class Fitted:
    """A beat timeline's measures, as TiLiA shows them once it has fitted its
    lists to its beats: the beats in each measure, in time order, and each
    measure's printed number.

    `problem` is set when TiLiA can't open the timeline: the list at fault
    and why. The measures are then those TiLiA would show before it fails,
    none past the last beat."""

    counts: list[int]
    numbers: list[int]
    problem: tuple[str, str] | None = None


def pattern_bars(pattern: Any) -> list[int]:
    """The bar lengths a beat pattern gives, by the core's parser; one that
    doesn't parse counts as "4", the default (FR-084;
    TimeLineAnnotator/project-management#310)."""
    # Imported here: the time map imports this package.
    from tilia_core.timemap.pattern import parse

    if isinstance(pattern, str):
        parsed = parse(pattern)
        if parsed.is_complete:
            return parsed.bars
    return parse(TIMELINE_SHAPES["beat"].defaults["beat_pattern"]).bars


def fit(
    beat_count: int,
    beats_in_measure: Any,
    measure_numbers: Any,
    pattern: Sequence[int],
) -> Fitted:
    """Fit an old file's lists by measure to its `beat_count` beats, as TiLiA
    does when it opens the file. A missing list is an empty one."""
    counts, counts_read = _whole_numbers(beats_in_measure, minimum=1)
    numbers, numbers_read = _whole_numbers(measure_numbers)
    if not counts_read:
        reason = '"beats_in_measure" isn\'t a list of whole numbers from 1'
        return _shown(beat_count, counts, numbers, ("beats_in_measure", reason))
    if not numbers_read:
        reason = '"measure_numbers" isn\'t a list of whole numbers'
        return _shown(beat_count, counts, numbers, ("measure_numbers", reason))
    delta = beat_count - sum(counts)
    if delta > 0:
        counts = _extended(counts, list(pattern), delta)
        # extend_measure_numbers
        while len(numbers) < len(counts):
            numbers.append(numbers[-1] + 1 if numbers else 1)
    elif delta < 0:
        counts = _reduced(counts, -delta)
    if len(numbers) < len(counts):
        # TiLiA's Beat.metric_position reads a number for every measure.
        reason = f"it has {len(counts)} measures but {len(numbers)} measure numbers"
        return _shown(beat_count, counts, numbers, ("measure_numbers", reason))
    return Fitted(counts, numbers[: len(counts)])


def _whole_numbers(value: Any, minimum: int | None = None) -> tuple[list[int], bool]:
    """A list of whole numbers, as TiLiA reads it, and whether all of it could
    be read: a missing list is an empty one; else the items before the first
    that isn't a whole number, or is below `minimum`. A number written with a
    fraction of zero, such as 4.0, is a whole number."""
    if value is None:
        return [], True
    if not isinstance(value, list):
        return [], False
    read: list[int] = []
    for item in value:
        if isinstance(item, float) and item.is_integer():
            item = int(item)
        if isinstance(item, bool) or not isinstance(item, int):
            return read, False
        if minimum is not None and item < minimum:
            return read, False
        read.append(item)
    return read, True


def _shown(
    beat_count: int,
    counts: list[int],
    numbers: list[int],
    problem: tuple[str, str],
) -> Fitted:
    """The measures TiLiA would show before it fails: those with both a count
    and a number, up to the last beat."""
    shown: list[int] = []
    start = 0
    for count in counts[: min(len(counts), len(numbers))]:
        if start >= beat_count:
            break
        shown.append(min(count, beat_count - start))
        start += count
    return Fitted(shown, numbers[: len(shown)], problem)


def _extension(
    pattern: list[int], amount: int, start_index: int, on_start: int
) -> list[int]:
    """`get_extension_from_beat_pattern`: the measures `amount` more beats
    make, following the pattern cyclically from `start_index`. With
    `on_start`, the beats already in the measure at `start_index`, the first
    entry tops that measure up; a measure as full as its pattern entry, or
    fuller, has nothing to top up (TiLiA 0.7.1)."""
    if amount == 0:
        return []
    cycle = itertools.cycle(pattern)
    for _ in range(start_index % len(pattern)):  # TiLiA steps start_index times
        next(cycle)
    extension: list[int] = []
    remaining = amount
    if on_start:
        beats = next(cycle)
        if on_start < beats:
            extension = [min(beats - on_start, amount)]
            remaining = amount - (beats - on_start)
    for beats in cycle:
        if remaining <= 0:
            break
        extension.append(min(beats, remaining))
        remaining -= beats
    return extension


def _extended(counts: list[int], pattern: list[int], amount: int) -> list[int]:
    """`extend_beats_in_measure`, with `_get_beats_in_measure_extension`."""
    if not counts:
        return _extension(pattern, amount, 0, 0)
    measure_count = len(counts)
    # The last measure's pattern entry: TiLiA writes its index two ways,
    # which give the same entry. Its test for an index of -1 never holds,
    # since Python's % is never negative there.
    start_index = (measure_count % len(pattern) - 1) % measure_count
    extension = _extension(pattern, amount, start_index, counts[-1])
    if counts[-1] >= pattern[measure_count % len(pattern) - 1]:
        return counts + extension
    return counts[:-1] + [counts[-1] + extension[0]] + extension[1:]


def _reduced(counts: list[int], amount: int) -> list[int]:
    """`reduce_beats_in_measure`: `amount` beats off the end, dropping the
    measures that empty."""
    counts = list(counts)
    remaining = amount
    while counts and remaining > 0:
        if counts[-1] <= remaining:
            remaining -= counts.pop()
        else:
            counts[-1] -= remaining
            remaining = 0
    return counts


def marks(
    fitted: Fitted, measures_to_force_display: Any, beat_count: int
) -> dict[int, dict[str, Any]]:
    """Each measure's mark, by the index of its first beat among the beats in
    time order: its number on the first measure always, and later where it
    isn't the previous measure's plus one; `force_display` where TiLiA always
    shows its number. With no measure, the first beat still starts one, the
    first, numbered 1 (FR-081)."""
    counts, numbers = fitted.counts, fitted.numbers
    if not counts:
        return {0: {"number": 1}} if beat_count else {}
    shown = _forced(measures_to_force_display, len(counts))
    found: dict[int, dict[str, Any]] = {}
    start = 0
    for index, (count, number) in enumerate(zip(counts, numbers, strict=True)):
        mark: dict[str, Any] = {}
        if index == 0 or number != numbers[index - 1] + 1:
            mark["number"] = number
        if index in shown:
            mark["force_display"] = True
        found[start] = mark
        start += count
    return found


def _forced(value: Any, measure_count: int) -> set[int]:
    """The measures whose number is always shown, as TiLiA keeps them when it
    opens a file: those of the timeline's measures, once each."""
    if not isinstance(value, list):
        return set()
    forced = set()
    for item in value:
        if isinstance(item, float) and item.is_integer():
            item = int(item)
        if isinstance(item, int) and not isinstance(item, bool):
            if 0 <= item < measure_count:
                forced.add(item)
    return forced


def _default_beat_unit() -> dict[str, Any]:
    """T12's default, desktop#621's, marked assumed (FR-083)."""
    # Imported here: the time map imports this package.
    from tilia_core.timemap import units

    return {
        "denominator": units.DEFAULT_DENOMINATOR,
        "units": units.DEFAULT_UNITS,
        "assumed": True,
    }


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def convert(
    old: dict[str, Any],
    content: dict[str, Any],
    warnings: list[ReadWarning],
    changes: dict[str, int],
) -> None:
    """Turn the beat timelines of an old file's content, in the current
    format but with the old ids, into marks on their downbeats, in place.
    `old` is the old file's content, with its timelines under the same ids.
    What is dropped is added to `warnings`, with its place in the old file,
    and the measures with more than one beat unit are counted in
    `changes`."""
    for key, timeline in content["timelines"].items():
        if timeline_kind_from_file(timeline["kind"]) != "beat":
            continue
        place = pointer_to("/timelines", key)
        before = old["timelines"][key]
        if before.get("show_time_signatures") is None:
            # Files from before time signatures: written, since the default
            # is true (desktop#621's rule).
            timeline["show_time_signatures"] = False
        _Converted(timeline, place, warnings, changes).convert()


class _Converted:
    """One beat timeline, converted in place."""

    def __init__(
        self,
        timeline: dict[str, Any],
        place: str,
        warnings: list[ReadWarning],
        changes: dict[str, int],
    ) -> None:
        self.timeline = timeline
        self.place = place
        self.warnings = warnings
        self.changes = changes

    def _warn(self, place: str, message: str) -> None:
        self.warnings.append(ReadWarning(place=place, line=None, message=message))

    def _at(self, component_id: str) -> str:
        return pointer_to(pointer_to(self.place, "components"), component_id)

    def convert(self) -> None:
        timeline = self.timeline
        components: dict[str, Any] = timeline["components"]
        lists = {name: timeline.pop(name, None) for name in _LISTS}
        timeline["measure_source"] = "unknown"
        beats = self.beats(components)
        if any(not _is_number(beat["time"]) for _, beat in beats):
            return  # a time that isn't a number: the check refuses it
        beats.sort(key=lambda item: item[1]["time"])
        fitted = fit(
            len(beats),
            lists["beats_in_measure"],
            lists["measure_numbers"],
            pattern_bars(timeline.get("beat_pattern")),
        )
        if fitted.problem is not None:
            name, reason = fitted.problem
            self._warn(
                pointer_to(self.place, name),
                f"TiLiA can't open {self.which()}: {reason}; its beats are kept,"
                " with marks on the measures TiLiA would show before that",
            )
        found = marks(fitted, lists["measures_to_force_display"], len(beats))
        for index, mark in found.items():
            beats[index][1]["measure"] = mark
        self.beat_units(components, dict(beats))
        if beats and not any("beat_unit" in beat for _, beat in beats):
            beats[0][1]["beat_unit"] = _default_beat_unit()
        rows = measures_of(dict(beats), "unknown")
        two = sum(1 for row in rows if len(row.beat_units) > 1)
        if two:
            self.changes[TWO_BEAT_UNITS] = self.changes.get(TWO_BEAT_UNITS, 0) + two

    def which(self) -> str:
        """The timeline, as a warning names it."""
        name = self.timeline.get("name")
        if not isinstance(name, str) or not name:
            return "a beat timeline without a name"
        quoted = json.dumps(nfc(name), ensure_ascii=False)
        return f"the beat timeline {printable(quoted)}"

    def beats(self, components: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        """The beats TiLiA keeps when it opens the file, in the file's order:
        a beat without a time, or at the time of a beat before it, is dropped
        from `components`, with a warning, as TiLiA drops it."""
        kept: list[tuple[str, dict[str, Any]]] = []
        times: set[int | float] = set()
        for component_id, component in list(components.items()):
            if component.get("kind") != "BEAT":
                continue
            time = component.get("time")
            if time is None:
                message = "a beat without a time"
            elif _is_number(time) and time in times:
                shown = printable(json.dumps(time))
                message = f"a beat at the same time as another ({shown})"
            else:
                if _is_number(time):
                    times.add(time)
                kept.append((component_id, component))
                continue
            del components[component_id]
            self._warn(
                self._at(component_id),
                f"{message} dropped, as TiLiA drops it when it opens the file",
            )
        return kept

    def beat_units(
        self, components: dict[str, Any], beats: dict[str, dict[str, Any]]
    ) -> None:
        """desktop#621's beat units, moved onto the beats they name, without
        the beat's id: the first on each beat, as TiLiA keeps it. One that
        names no beat TiLiA keeps, or a beat that has one already, is dropped,
        with a warning."""
        for component_id, component in list(components.items()):
            if component.get("kind") != _UNIT:
                continue
            del components[component_id]
            named = component.get("beat_id")
            if isinstance(named, int) and not isinstance(named, bool):
                named = str(named)
            beat = beats.get(named) if isinstance(named, str) else None
            if beat is None:
                shown = printable(json.dumps(component.get("beat_id")))
                reason = f"names {shown}, which isn't a beat TiLiA keeps"
            elif "beat_unit" in beat:
                reason = "is on a beat that has one already"
            else:
                unit = {
                    name: value
                    for name, value in component.items()
                    if name not in ("kind", "beat_id") and value is not None
                }
                if unit.get("assumed") is False:
                    del unit["assumed"]  # its default
                beat["beat_unit"] = unit
                continue
            self._warn(
                self._at(component_id),
                f"a beat unit that {reason} dropped, as TiLiA drops it when it"
                " opens the file",
            )
