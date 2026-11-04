"""Markers from a CSV with times: TiLiA's importer, moved into the core."""

from __future__ import annotations

import os
from pathlib import Path

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

_DEFAULTS = COMPONENT_SHAPES["marker"].defaults
_TEXTS = ("label", "comments")


def import_by_time(
    document: tla.Document, target: str, path: str | os.PathLike[str]
) -> ImportResult:
    """Replace the markers of the timeline `target` with a CSV's, in memory.

    `time` is required; `label` and `comments` are optional. A row that can't be
    read, or that the rules refuse, is skipped and reported. Raises `ImportFailed`
    when the import can't run, and `OSError` for a file that can't be opened; both
    change nothing.
    """
    path = Path(path)
    if document.media_length is None:
        raise ImportFailed(path, NO_MEDIA_LENGTH)
    header, rows = read_csv(path)
    if "time" not in header:
        raise ImportFailed(path, COLUMN_NOT_FOUND.format("time"))

    problems: list[RowProblem] = []
    built: list[tuple[CsvRow, tla.Component]] = []
    for row in rows:
        cell = row.values.get("time", "")
        try:
            time = float(cell)
        except ValueError:
            problems.append(_skipped(path, row, rules.not_valid("time", cell)))
            continue
        texts = {name: row.values[name] for name in _TEXTS if name in row.values}
        attrs = {**_DEFAULTS, **texts, "time": time}
        built.append((row, tla.Component(id=tla.new_id(), kind="marker", attrs=attrs)))

    checked = rules.check_timeline(
        document.media_length, [component for _, component in built], skip_broken=True
    )
    kept: list[tla.Component] = []
    for row, component in built:
        outcome = checked[component.id].outcome
        if outcome:
            kept.append(component)
        else:
            problems.append(_skipped(path, row, outcome.reason))

    problems.sort(key=lambda problem: problem.line)
    commit(document, target, kept)
    return ImportResult(
        created=[component.id for component in kept],
        rows=len(rows),
        problems=problems,
    )


def _skipped(path: Path, row: CsvRow, message: str) -> RowProblem:
    # Every rule a marker can break here is about its time.
    return RowProblem(
        path=path, line=row.line, column="time", message=message, skipped=True
    )
