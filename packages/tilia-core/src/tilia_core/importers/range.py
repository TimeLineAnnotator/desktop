"""Ranges from a CSV, as TiLiA's range importer reads them.

Rows are made by name, in order of appearance. Every range is built first, then
checked with the rules; joins are made among the ranges the check kept, and
checked with them, as TiLiA joins only the ranges it created.
"""

from __future__ import annotations

import bisect
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tilia_core import rules, tla
from tilia_core.importers._commit import commit, new_row_id
from tilia_core.importers._csv import CsvRow, read_csv
from tilia_core.importers._results import ImportFailed, ImportResult, RowProblem
from tilia_core.tla.layout import COMPONENT_SHAPES

# TiLiA's texts: tilia/parsers/csv/base.py's and range.py's, and tilia/errors.py's
# for a timeline added before the length is known. A file can bring a timeline with
# no length, which is the same state (TimeLineAnnotator/project-management#418).
_COLUMN_NOT_FOUND = "Column '{}' not found on first row of .csv file."
_EMPTY_ROW_NAME = "row name is empty; skipping."
_NO_MEDIA_LENGTH = (
    "No media loaded and no duration set. Load a media file with 'load-media' or"
    " set a duration with 'metadata set-media-length'."
)

_DEFAULTS = COMPONENT_SHAPES["range"].defaults
_REQUIRED = ("start", "end", "row")
_TIMES = ("start", "end")
_TEXTS = ("label", "comments")
_FLAG = "joined_with_next"


@dataclass(frozen=True)
class _Built:
    """A range built from a row of the CSV, before it is checked."""

    component: tla.Component
    line: int
    joined_with_next: bool
    # The `joined_with_next` cell, when it isn't a boolean and so read as false.
    not_a_flag: str | None


def import_by_time(
    document: tla.Document, target: str, path: str | os.PathLike[str]
) -> ImportResult:
    """Replace the ranges and the rows of the range timeline `target` with a CSV's,
    in memory.

    `start`, `end` and `row` are required; `label`, `color`, `comments` and
    `joined_with_next` are optional. Times are read in the document's time unit. A
    row that can't be read, or that the rules refuse, is skipped and reported, and
    only that. In a row that is kept, a color that isn't one is replaced by the
    default, with a note; a `joined_with_next` that isn't a boolean reads as false,
    with a note; and a join that can't be made is dropped, with the range kept and
    the problem reported.

    Raises `ImportFailed` when the import can't run, and `OSError` for a file that
    can't be opened; both change nothing.
    """
    path = Path(path)
    if document.media_length is None:
        raise ImportFailed(path, _NO_MEDIA_LENGTH)
    header, csv_rows = read_csv(path)
    for column in _REQUIRED:
        if column not in header:
            raise ImportFailed(path, _COLUMN_NOT_FOUND.format(column))

    problems: list[RowProblem] = []
    rows: list[dict[str, Any]] = []
    built = [
        one
        for csv_row in csv_rows
        if (one := _read_row(csv_row, rows, path, problems)) is not None
    ]
    kept = _kept(document.media_length, built, rows, path, problems)
    _make_joins(document.media_length, kept, rows, path, problems)

    components = [one.component for one in kept]
    # With no range kept, the timeline gets its one blank row, whatever rows the
    # refused ones named (the spec's edge cases).
    commit(document, target, components, rows=rows if components else [])
    # In the CSV's order, whichever step found each: reading, the rules, a join.
    problems.sort(key=lambda problem: problem.line)
    return ImportResult(
        created=[component.id for component in components],
        rows=len(csv_rows),
        problems=problems,
    )


def _read_row(
    csv_row: CsvRow,
    rows: list[dict[str, Any]],
    path: Path,
    problems: list[RowProblem],
) -> _Built | None:
    """The range a row of the CSV holds, or None when it can't be read.

    A row with times that can be read and a row name makes its row, whether or not
    the rules then keep its range, as TiLiA makes it before creating the range.
    """
    values = csv_row.values
    times: dict[str, float] = {}
    for column in _TIMES:
        cell = values.get(column, "")
        try:
            times[column] = float(cell)
        except ValueError:
            problems.append(
                _problem(path, csv_row.line, column, rules.not_valid(column, cell))
            )
            return None
    name = values.get("row")
    if not name:
        problems.append(_problem(path, csv_row.line, "row", _EMPTY_ROW_NAME))
        return None
    row_id = _get_or_create_row(rows, name)

    flag = values.get(_FLAG, "")
    joined_with_next = _parse_optional_bool(flag)

    attrs = {
        **_DEFAULTS,
        **times,
        "row_id": row_id,
        **{text: values[text] for text in _TEXTS if text in values},
    }
    if values.get("color"):
        attrs["color"] = values["color"]
    component = tla.Component(id=tla.new_id(), kind="range", attrs=attrs)
    return _Built(
        component,
        csv_row.line,
        bool(joined_with_next),
        flag if joined_with_next is None else None,
    )


def _get_or_create_row(rows: list[dict[str, Any]], name: str) -> str:
    """The id of the row with that name, made when there is none yet."""
    for row in rows:
        if row["name"] == name:
            return row["id"]
    row_id = new_row_id({row["id"] for row in rows})
    rows.append({"id": row_id, "name": name, "color": None, "height": None})
    return row_id


def _parse_optional_bool(value: str) -> bool | None:
    """A strict boolean: `true` or `false` in any case, blank counting as `false`,
    as the beat importer reads `is_first_in_measure`. None for anything else."""
    text = value.strip().lower()
    if text in ("false", ""):
        return False
    if text == "true":
        return True
    return None


def _kept(
    media_length: float,
    built: Sequence[_Built],
    rows: Sequence[dict[str, Any]],
    path: Path,
    problems: list[RowProblem],
) -> list[_Built]:
    """The ranges the rules keep, in the order given. One whose `joined_with_next`
    isn't a boolean gets a note, and one whose color isn't one is kept with the
    default color, and a note; a range they refuse gets neither."""
    checked = rules.check_timeline(
        media_length, [one.component for one in built], rows=rows, skip_broken=True
    )
    kept = []
    for one in built:
        found = checked[one.component.id]
        if not found.outcome:
            reason = found.outcome.reason
            column = _column_of(reason, one.component.attrs)
            problems.append(_problem(path, one.line, column, reason))
            continue
        if one.not_a_flag is not None:
            note = rules.not_valid(_FLAG, one.not_a_flag)
            problems.append(_problem(path, one.line, _FLAG, note, skipped=False))
        if not found.color:
            one.component.attrs["color"] = _DEFAULTS["color"]
            reason = found.color.reason.removesuffix(".")
            problems.append(
                _problem(
                    path,
                    one.line,
                    "color",
                    f"{reason}: the default color is used.",
                    skipped=False,
                )
            )
        kept.append(one)
    return kept


def _column_of(reason: str, attrs: Mapping[str, Any]) -> str | None:
    """The column a rule's reason about `attrs` is about, when it is about one: the
    others are about a start and an end together."""
    for column in _TIMES:
        if reason == rules.not_valid(column, attrs[column]):
            return column
    return None


def _make_joins(
    media_length: float,
    kept: Sequence[_Built],
    rows: Sequence[dict[str, Any]],
    path: Path,
    problems: list[RowProblem],
) -> None:
    """Join each flagged range to the next range kept in its row, and check the joins.

    The next ranges are those that start first after it starts; of several, it is
    the first in the CSV. A join the rules refuse is dropped and reported, and the
    range is kept, also for the other joins.
    """
    flagged = [one for one in kept if one.joined_with_next]
    if not flagged:
        return

    by_row: dict[str, list[tla.Component]] = {}
    for one in kept:
        by_row.setdefault(one.component.attrs["row_id"], []).append(one.component)
    starts: dict[str, list[float]] = {}
    for row_id, ranges in by_row.items():
        # A stable sort keeps the CSV's order among those with one start.
        ranges.sort(key=lambda component: component.attrs["start"])
        starts[row_id] = [component.attrs["start"] for component in ranges]

    for one in flagged:
        attrs = one.component.attrs
        ranges = by_row[attrs["row_id"]]
        following = bisect.bisect_right(starts[attrs["row_id"]], attrs["start"])
        # The last range of its row names itself: the rules read that it is
        # flagged, and refuse it for having no next range, whatever it names.
        attrs["joined_right"] = (
            ranges[following].id if following < len(ranges) else one.component.id
        )

    checked = rules.check_timeline(
        media_length, [one.component for one in kept], rows=rows
    )
    for one in flagged:
        outcome = checked[one.component.id].outcome
        if not outcome:
            one.component.attrs["joined_right"] = _DEFAULTS["joined_right"]
            # `skipped`, for all that the row is imported: it is what makes this a
            # problem, not a note (TimeLineAnnotator/project-management#374).
            problems.append(_problem(path, one.line, _FLAG, outcome.reason))


def _problem(
    path: Path, line: int, column: str | None, message: str, *, skipped: bool = True
) -> RowProblem:
    return RowProblem(
        path=path, line=line, column=column, message=message, skipped=skipped
    )
