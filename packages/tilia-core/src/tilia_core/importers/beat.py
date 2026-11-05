"""Beats from a CSV, as measure marks and beat units: TiLiA's importer, moved into the core.

TiLiA keeps lists of beats per measure; the format marks each measure on its downbeat
(TimeLineAnnotator/project-management#161). So the rows are grouped as TiLiA groups
them, and the measures are written as marks, from which `tla.measure_table` builds
the table that the time map reads, as WP3's reader does when it reads a file.
"""

from __future__ import annotations

import itertools
import math
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tilia_core import rules, tla
from tilia_core.importers._commit import commit
from tilia_core.importers._csv import CsvRow, read_csv
from tilia_core.importers._results import ImportFailed, ImportResult, RowProblem
from tilia_core.importers.marker import COLUMN_NOT_FOUND, NO_MEDIA_LENGTH
from tilia_core.timemap import pattern, units
from tilia_core.tla.layout import COMPONENT_SHAPES, TIMELINE_SHAPES

# TiLiA's texts: tilia/parsers/csv/beat.py's, and the beat timeline's for a pattern
# that doesn't parse, without the timeline's memory address.
NOT_SORTED = "Time is not sorted in ascending order. Please sort before importing."
BAD_PATTERN = "Invalid beat pattern '{}': {} Using '{}' instead."
# As TimeLineAnnotator/desktop#816 (import_csv) words them. Provisional until
# TimeLineAnnotator/project-management#484 (what such a refusal says).
NOT_A_BEAT_TIMELINE = "{} is not a beat timeline"
NO_TIMELINE = "No timeline found with id={}"

_DEFAULTS = COMPONENT_SHAPES["beat"].defaults
_DEFAULT_PATTERN: str = TIMELINE_SHAPES["beat"].defaults["beat_pattern"]
_IS_FIRST = "is_first_in_measure"


@dataclass
class _Row:
    """A row of the CSV, as far as it could be read."""

    source: CsvRow
    flagged: bool  # its `is_first_in_measure` is true
    number: int | None  # the number it gives its measure
    # Its beat. None for a row that isn't imported: one that can't be read, or that
    # the rules refuse.
    beat: tla.Component | None


@dataclass
class _Measure:
    number: int
    force_display: bool = False
    beats: list[tla.Component] = field(default_factory=list)

    def add(self, row: _Row) -> None:
        if row.number is not None:
            self.number = row.number
            self.force_display = True
        if row.beat is not None:
            self.beats.append(row.beat)


def import_beats(
    document: tla.Document, target: str, path: str | os.PathLike[str]
) -> ImportResult:
    """Replace the beats of the beat timeline `target` with a CSV's, in memory, and
    rebuild its measure table, so that an import by measure finds its time map.

    `time` is required; `measure`, `is_first_in_measure`, `denominator` and `units`
    are optional. The beats are grouped by `is_first_in_measure` when the column is
    there, else by the timeline's beat pattern, cycling; a pattern that doesn't parse
    counts as the format's default, with a note. A number in `measure` is read on the
    rows `is_first_in_measure` marks, or on any row when there is no such column; it
    numbers its measure, and the later ones follow from it. A filled `denominator` or
    `units` puts a beat unit on its beat when it changes the one in force, the other
    carried over; the first beat gets the default, assumed, unless it has one.

    A row that can't be read, or that the rules refuse, is skipped and reported. A
    beat unit that can't be read is reported, and the beat kept without it. Raises
    `ImportFailed` when the import can't run, or the times are out of order, and
    `OSError` for a file that can't be opened; all change nothing.
    """
    path = Path(path)
    timeline = _beat_timeline(document, target, path)
    if document.media_length is None:
        raise ImportFailed(path, NO_MEDIA_LENGTH)
    header, csv_rows = read_csv(path)
    if "time" not in header:
        raise ImportFailed(path, COLUMN_NOT_FOUND.format("time"))
    has_flags = _IS_FIRST in header

    problems: list[RowProblem] = []
    rows = _read_rows(csv_rows, has_flags, path, problems)
    _refuse(document.media_length, rows, path, problems)

    notes: list[str] = []
    if has_flags:
        measures = _measures_by_flag(rows)
    else:
        bars, note = _pattern_bars(timeline)
        measures = _measures_by_pattern(rows, bars)
        if note and measures:
            notes.append(note)
    found = _mark(measures)
    _set_beat_units(rows, path, problems)

    kept = [row.beat for row in rows if row.beat is not None]
    attrs: dict[str, Any] = {"measure_source": "import"}
    found_pattern = pattern.format_bars(found)
    if pattern.parse(found_pattern).is_complete:
        attrs["beat_pattern"] = found_pattern

    problems.sort(key=lambda problem: problem.line)
    commit(document, target, kept, attrs=attrs)
    timeline.measures = tla.measure_table(timeline)
    return ImportResult(
        created=[component.id for component in kept],
        rows=len(csv_rows),
        problems=problems,
        notes=notes,
    )


def _beat_timeline(document: tla.Document, target: str, path: Path) -> tla.Timeline:
    try:
        timeline = document.timelines[target]
    except KeyError:
        raise ImportFailed(path, NO_TIMELINE.format(target)) from None
    if timeline.kind != "beat":
        named = f"'{timeline.name}'" if timeline.name else timeline.ordinal
        raise ImportFailed(path, NOT_A_BEAT_TIMELINE.format(f"Timeline {named}"))
    return timeline


def _read_rows(
    csv_rows: Iterable[CsvRow], has_flags: bool, path: Path, problems: list[RowProblem]
) -> list[_Row]:
    """The rows with what they say, each readable one with its beat. Raises
    `ImportFailed` for times out of order, which a row with a time that isn't a
    number takes no part in."""
    rows: list[_Row] = []
    latest = -math.inf
    for row in csv_rows:
        flagged = has_flags and row.values.get(_IS_FIRST, "").lower() == "true"
        cell = row.values.get("time", "")
        try:
            time = float(cell)
        except ValueError:
            time = None
            problems.append(_problem(path, row, "time", rules.not_valid("time", cell)))
        if time is not None and math.isfinite(time):
            if time < latest:
                raise ImportFailed(path, NOT_SORTED)
            latest = time

        number = None
        cell = row.values.get("measure", "")
        if cell and (flagged or not has_flags):
            number = _measure_number(cell)
            if number is None and time is not None:
                problems.append(
                    _problem(path, row, "measure", rules.not_valid("measure", cell))
                )
                time = None

        beat = None
        if time is not None:
            attrs = {**_DEFAULTS, "time": time}
            beat = tla.Component(id=tla.new_id(), kind="beat", attrs=attrs)
        rows.append(_Row(row, flagged, number, beat))
    return rows


def _measure_number(cell: str) -> int | None:
    """A cell's measure number: an integer of at least 0, the rule for a measure mark's
    number, which the core's rules don't give yet
    (TimeLineAnnotator/project-management#420); else None."""
    try:
        number = int(cell)
    except ValueError:
        return None
    return number if number >= 0 else None


def _refuse(
    media_length: float, rows: list[_Row], path: Path, problems: list[RowProblem]
) -> None:
    """Check the beats once, each with the earlier ones kept. A beat that breaks a rule
    is reported, and its row left without it."""
    built = [row for row in rows if row.beat is not None]
    checked = rules.check_timeline(
        media_length, [row.beat for row in built], skip_broken=True
    )
    for row in built:
        outcome = checked[row.beat.id].outcome
        if not outcome:
            # Every rule a beat can break here is about its time.
            problems.append(_problem(path, row.source, "time", outcome.reason))
            row.beat = None


def _pattern_bars(timeline: tla.Timeline) -> tuple[list[int], str | None]:
    """The bars of the timeline's pattern; those of the format's default, and a note,
    for one that doesn't parse
    (TimeLineAnnotator/project-management#310, a beat pattern that doesn't parse)."""
    value = timeline.attrs.get("beat_pattern")
    text = _DEFAULT_PATTERN if value is None else str(value)
    parsed = pattern.parse(text)
    if parsed.is_complete:
        return parsed.bars, None
    note = BAD_PATTERN.format(text, parsed.error, _DEFAULT_PATTERN)
    return pattern.parse(_DEFAULT_PATTERN).bars, note


def _measures_by_flag(rows: Iterable[_Row]) -> list[_Measure]:
    """The measures the rows mark, as TiLiA counts them: a measure starts at the first
    row, and at each row `is_first_in_measure` marks. Every row counts, so a measure
    whose downbeat isn't imported starts at its next beat, as when a downbeat is
    deleted (`tla.model`), and the measures after it keep their numbers."""
    measures: list[_Measure] = []
    for row in rows:
        if row.flagged or not measures:
            measures.append(_Measure(measures[-1].number + 1 if measures else 1))
        measures[-1].add(row)
    return measures


def _measures_by_pattern(rows: Iterable[_Row], bars: list[int]) -> list[_Measure]:
    """The beats imported, grouped by bar lengths, cycling. Only they count: the rows
    say nothing about where a measure starts."""
    measures: list[_Measure] = []
    lengths = itertools.cycle(bars)
    length = next(lengths)
    for row in rows:
        if row.beat is None:
            continue
        if not measures:
            measures.append(_Measure(1))
        elif len(measures[-1].beats) >= length:
            length = next(lengths)
            measures.append(_Measure(measures[-1].number + 1))
        measures[-1].add(row)
    return measures


def _mark(measures: Iterable[_Measure]) -> list[int]:
    """Put a mark on the first beat of each measure that has one, as the format stores
    it, and give how many beats each has. The writer writes a number whenever it is
    set, so only those that don't follow from the previous measure are."""
    bars: list[int] = []
    previous: int | None = None
    for measure in measures:
        if not measure.beats:
            continue
        mark: dict[str, Any] = {}
        if measure.number != (1 if previous is None else previous + 1):
            mark["number"] = measure.number
        if measure.force_display:
            mark["force_display"] = True
        measure.beats[0].attrs["measure"] = mark
        previous = measure.number
        bars.append(len(measure.beats))
    return bars


def _set_beat_units(
    rows: Iterable[_Row], path: Path, problems: list[RowProblem]
) -> None:
    """Put the beat units on the beats imported. A value left empty, and what follows
    a value that can't be read, take the last one read from a beat imported."""
    denominator, text = units.DEFAULT_DENOMINATOR, units.DEFAULT_UNITS
    any_set = False
    first: tla.Component | None = None
    for row in rows:
        if row.beat is None:
            continue
        first = first or row.beat
        read = _read_beat_unit(row.source, path, denominator, text)
        if read is None:
            continue
        if isinstance(read, RowProblem):
            problems.append(read)
            continue
        if any_set and read == (denominator, text):
            continue
        denominator, text = read
        row.beat.attrs["beat_unit"] = {"denominator": denominator, "units": text}
        any_set = True
    if first is not None and "beat_unit" not in first.attrs:
        first.attrs["beat_unit"] = {
            "denominator": units.DEFAULT_DENOMINATOR,
            "units": units.DEFAULT_UNITS,
            "assumed": True,
        }


def _read_beat_unit(
    row: CsvRow, path: Path, denominator: int, text: str
) -> tuple[int, str] | RowProblem | None:
    """The beat unit a row gives, the other value carried over; None when it gives
    none. A row's first value that can't be read is its problem."""
    denominator_cell = row.values.get("denominator", "").strip()
    units_cell = row.values.get("units", "").strip()
    if not denominator_cell and not units_cell:
        return None
    if denominator_cell:
        try:
            denominator = int(denominator_cell)
        except ValueError:
            denominator = 0
        if not units.validate_denominator(denominator):
            message = rules.not_valid("denominator", denominator_cell)
            return _problem(path, row, "denominator", message, skipped=False)
    if units_cell:
        parsed = units.parse_units(units_cell)
        if not parsed.is_valid:
            message = rules.not_valid("units", units_cell)
            return _problem(path, row, "units", message, skipped=False)
        text = units.format_units(parsed.units)
    return denominator, text


def _problem(
    path: Path, row: CsvRow, column: str, message: str, *, skipped: bool = True
) -> RowProblem:
    return RowProblem(
        path=path, line=row.line, column=column, message=message, skipped=skipped
    )
