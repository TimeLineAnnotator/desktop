"""Hierarchies from a CSV with times: TiLiA's importer, moved into the core."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from tilia_core import rules, tla
from tilia_core.importers._commit import commit
from tilia_core.importers._csv import CsvRow, read_csv
from tilia_core.importers._results import ImportFailed, ImportResult, RowProblem
from tilia_core.tla.layout import COMPONENT_SHAPES

# TiLiA's texts: tilia/parsers/csv/base.py's, and tilia/errors.py's for a timeline
# added before the length is known. A file can bring a timeline with no length,
# which is the same state (TimeLineAnnotator/project-management#418).
COLUMN_NOT_FOUND = "Column '{}' not found on first row of .csv file."
NO_MEDIA_LENGTH = (
    "No media loaded and no duration set. Load a media file with 'load-media' or"
    " set a duration with 'metadata set-media-length'."
)
FORMAL_COLUMNS_NOTE = "formal_type and formal_function are no longer stored"

_DEFAULTS = COMPONENT_SHAPES["hierarchy"].defaults
_REQUIRED = ("start", "end", "level")
_TEXTS = ("label", "color", "comments")
_FORMAL_COLUMNS = ("formal_type", "formal_function")
_NUMBERS: tuple[tuple[str, Callable[[str], float]], ...] = (
    ("start", float),
    ("end", float),
    ("level", int),
    ("pre_start", float),
    ("post_end", float),
)
# Unset, they follow the start and the end when those move, where a number stays
# fixed; so one equal to its start or end is left unset, as an empty cell is.
_FOLLOWS = {"pre_start": "start", "post_end": "end"}
# How the rules' reasons start, for each column they can be about. A reason for a
# value that isn't one ends in `rules.not_valid`'s text for its column instead.
# Those about the place in the timeline (another at the same place, one it crosses)
# aren't about one column.
_REASON_STARTS = (
    ("Start time", "start"),
    ("End time", "end"),
    ("Level", "level"),
    ("pre_start", "pre_start"),
    ("post_end", "post_end"),
)


def import_by_time(
    document: tla.Document, target: str, path: str | os.PathLike[str]
) -> ImportResult:
    """Replace the hierarchies of the timeline `target` with a CSV's, in memory.

    `start`, `end` and `level` are required; `pre_start`, `post_end`, `label`,
    `color` and `comments` are optional. A row that can't be read, or that the
    rules refuse, is skipped and reported; a color that isn't one is replaced by
    the default, with a note. `formal_type` and `formal_function` are ignored, with
    a note. Raises `ImportFailed` when the import can't run, and `OSError` for a
    file that can't be opened; both change nothing.
    """
    path = Path(path)
    if document.media_length is None:
        raise ImportFailed(path, NO_MEDIA_LENGTH)
    header, rows = read_csv(path)
    for column in _REQUIRED:
        if column not in header:
            raise ImportFailed(path, COLUMN_NOT_FOUND.format(column))

    problems: list[RowProblem] = []
    built: list[tuple[CsvRow, tla.Component]] = []
    for row in rows:
        attrs = _attrs(row.values, path, row.line)
        if isinstance(attrs, RowProblem):
            problems.append(attrs)
        else:
            built.append(
                (row, tla.Component(id=tla.new_id(), kind="hierarchy", attrs=attrs))
            )

    checked = rules.check_timeline(
        document.media_length, [component for _, component in built], skip_broken=True
    )
    kept: list[tla.Component] = []
    for row, component in built:
        found = checked[component.id]
        if not found.outcome:
            problems.append(
                RowProblem(
                    path=path,
                    line=row.line,
                    column=_column_of(found.outcome.reason),
                    message=found.outcome.reason,
                    skipped=True,
                )
            )
            continue
        if not found.color:
            component.attrs["color"] = _DEFAULTS["color"]
            problems.append(
                RowProblem(
                    path=path,
                    line=row.line,
                    column="color",
                    message=(
                        f"{found.color.reason.removesuffix('.')}:"
                        " the default color is used."
                    ),
                    skipped=False,
                )
            )
        kept.append(component)

    problems.sort(key=lambda problem: problem.line)
    commit(document, target, kept)
    return ImportResult(
        created=[component.id for component in kept],
        rows=len(rows),
        problems=problems,
        notes=(
            [FORMAL_COLUMNS_NOTE]
            if any(column in header for column in _FORMAL_COLUMNS)
            else []
        ),
    )


def _attrs(
    values: Mapping[str, str], path: Path, line: int
) -> dict[str, Any] | RowProblem:
    """A row's attributes, or why it can't be read: the first cell that can't."""
    attrs: dict[str, Any] = {
        **_DEFAULTS,
        **{name: values[name] for name in _TEXTS if name in values},
    }
    for column, read in _NUMBERS:
        cell = values.get(column, "")
        if column in _FOLLOWS and cell == "":
            continue
        try:
            attrs[column] = read(cell)
        except ValueError:
            return RowProblem(
                path=path,
                line=line,
                column=column,
                message=rules.not_valid(column, cell),
                skipped=True,
            )
    for column, followed in _FOLLOWS.items():
        if attrs.get(column) == attrs[followed]:
            del attrs[column]
    return attrs


def _column_of(reason: str) -> str | None:
    """The column a rule's reason is about, when it is about one."""
    for start, column in _REASON_STARTS:
        if reason.startswith(start):
            return column
    for column, _ in _NUMBERS:
        if reason.endswith(rules.not_valid(column, "")):
            return column
    return None
