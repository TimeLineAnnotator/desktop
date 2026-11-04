"""PDF page markers from a CSV, as TiLiA's PDF importer reads them.

Page numbers are checked against the PDF's page count, read with pypdf. A PDF
that can't be found or read counts 0 pages, as in TiLiA, so every row is refused.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from pathlib import Path

import pypdf

from tilia_core import rules, tla
from tilia_core.importers._commit import commit
from tilia_core.importers._csv import CsvRow, read_csv
from tilia_core.importers._results import ImportFailed, ImportResult, RowProblem

logger = logging.getLogger(__name__)

# pypdf logs what it finds in a broken file, which goes to standard error when
# nothing has set up logging; `tilia run`'s standard error holds its reports only.
logging.getLogger("pypdf").addHandler(logging.NullHandler())

# TiLiA's texts: tilia/parsers/csv/base.py's, and tilia/errors.py's for a timeline
# added before the length is known. A file can bring a timeline with no length,
# which is the same state (TimeLineAnnotator/project-management#418).
_COLUMN_NOT_FOUND = "Column '{}' not found on first row of .csv file."
_NO_MEDIA_LENGTH = (
    "No media loaded and no duration set. Load a media file with 'load-media' or"
    " set a duration with 'metadata set-media-length'."
)
_CANT_BE_READ = "The PDF '{}' can't be read: every page number is refused"

_REQUIRED = ("page_number", "time")  # in the order TiLiA looks for them
_NUMBERS: tuple[tuple[str, Callable[[str], float]], ...] = (
    ("time", float),
    ("page_number", int),
)


def import_by_time(
    document: tla.Document, target: str, path: str | os.PathLike[str]
) -> ImportResult:
    """Replace the markers of the PDF timeline `target` with a CSV's, in memory.

    `time` and `page_number` are required. Times are read in the document's time
    unit. A row that can't be read, or that the rules refuse, is skipped and
    reported.

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

    stored = document.timelines[target].attrs.get("path", "")
    pdf = _pdf_file(stored, document.origin)
    page_count = None if pdf is None else _page_count(pdf)
    notes = [] if page_count is not None else [_CANT_BE_READ.format(pdf or stored)]

    problems: list[RowProblem] = []
    built: list[tuple[CsvRow, tla.Component]] = []
    for csv_row in csv_rows:
        attrs = _attrs(csv_row, path)
        if isinstance(attrs, RowProblem):
            problems.append(attrs)
        else:
            component = tla.Component(id=tla.new_id(), kind="pdf_marker", attrs=attrs)
            built.append((csv_row, component))

    checked = rules.check_timeline(
        document.media_length,
        [component for _, component in built],
        page_count=page_count or 0,
        skip_broken=True,
    )
    kept: list[tla.Component] = []
    for csv_row, component in built:
        outcome = checked[component.id].outcome
        if outcome:
            kept.append(component)
        else:
            problems.append(
                _problem(path, csv_row, _column_of(outcome.reason), outcome.reason)
            )

    commit(document, target, kept)
    # In the CSV's order, whichever step found each: reading or the rules.
    problems.sort(key=lambda problem: problem.line)
    return ImportResult(
        created=[component.id for component in kept],
        rows=len(csv_rows),
        problems=problems,
        notes=notes,
    )


def _attrs(csv_row: CsvRow, path: Path) -> dict[str, float] | RowProblem:
    """A row's attributes, or why it can't be read: the first cell that can't."""
    attrs: dict[str, float] = {}
    for column, read in _NUMBERS:
        cell = csv_row.values.get(column, "")
        try:
            attrs[column] = read(cell)
        except ValueError:
            return _problem(path, csv_row, column, rules.not_valid(column, cell))
    return attrs


def _column_of(reason: str) -> str:
    """The column a rule's reason is about: the page's, or the time's for the rest."""
    return "page_number" if reason.startswith("The PDF") else "time"


def _problem(path: Path, csv_row: CsvRow, column: str, message: str) -> RowProblem:
    return RowProblem(
        path=path, line=csv_row.line, column=column, message=message, skipped=True
    )


def _pdf_file(stored: str, origin: Path | None) -> Path | None:
    """The file a PDF timeline's `path` names: a relative one, from the folder of
    the document's file. Without that folder, only an absolute path names one, as
    a stored path is never read from where the process happens to run."""
    if not stored:
        return None
    pdf = Path(stored)
    if pdf.is_absolute():
        return pdf
    return None if origin is None else origin.parent / pdf


def _page_count(pdf: Path) -> int | None:
    """The PDF's page count; None when it can't be found or read."""
    try:
        return len(pypdf.PdfReader(pdf).pages)
    except Exception as error:  # pypdf raises many kinds, on a file it can't read
        logger.debug("can't read the PDF %s: %r", pdf, error)
        return None
