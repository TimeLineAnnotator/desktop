"""Importing CSV and JSON files into a document: TiLiA's importers, moved into the core."""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Callable
from pathlib import Path

from tilia_core import rules, tla
from tilia_core.importers._results import ImportFailed, ImportResult, RowProblem
from tilia_core.importers.hierarchy import import_by_time as hierarchy_by_time
from tilia_core.importers.marker import import_by_time as marker_by_time
from tilia_core.importers.metadata import import_metadata
from tilia_core.importers.pdf import import_by_time as pdf_by_time
from tilia_core.importers.range import import_by_time as range_by_time
from tilia_core.tla.model import Kind

__all__ = [
    "ImportFailed",
    "ImportResult",
    "RowProblem",
    "harmony_available",
    "import_csv",
    "import_metadata",
]

# TiLiA's texts: tilia/parsers/__init__.py's and tilia/ui/cli/timelines/imp.py's.
_BAD_BY = "'by' must be either 'time' or 'measure'"
_NO_REFERENCE = "Reference beat timeline is required for importing by measure"
# TiLiA's form, `{tl} is not a {kind} timeline`, can't be word for word: its kind is
# the one the command asked for, and its `{tl}` a memory address. So the timeline is
# named by its kind, name and ordinal, and the kinds a target can be are listed
# (TimeLineAnnotator/project-management#484, answered).
_NOT_IMPORTED_INTO = "{} is not a marker, hierarchy, range, harmony or pdf timeline"
_NOT_A_BEAT_TIMELINE = "{} is not a beat timeline"
_NO_TIMELINE = "No timeline found with id={}"
_HARMONY_NEEDS = f"harmony import needs: {rules.INSTALL_HARMONY}"


def _harmony_by_time(
    document: tla.Document, target: str, path: str | os.PathLike[str]
) -> ImportResult:
    raise NotImplementedError("Harmonies can't be imported yet")


_BY_TIME: dict[
    Kind, Callable[[tla.Document, str, str | os.PathLike[str]], ImportResult]
] = {
    "marker": marker_by_time,
    "hierarchy": hierarchy_by_time,
    "range": range_by_time,
    "harmony": _harmony_by_time,
    "pdf": pdf_by_time,
}


def import_csv(
    document: tla.Document,
    target: str,
    path: str | os.PathLike[str],
    *,
    by: str,
    reference: str | None = None,
) -> ImportResult:
    """Import a CSV into the timeline `target`, in memory, with the importer of its
    kind: marker, hierarchy, range, harmony or pdf.

    `by` is "time" or "measure"; `reference` is the id of the beat timeline to read
    measures from, and is read by measure only.

    Raises `ImportFailed` when the import can't run, and `OSError` for a file that
    can't be opened; both change nothing. By measure, and for a harmony timeline
    with the `harmony` extra, raises `NotImplementedError` for now.
    """
    path = Path(path)
    timeline = _timeline(document, target, path)
    if timeline.kind not in _BY_TIME:
        raise ImportFailed(path, _NOT_IMPORTED_INTO.format(_named(timeline)))
    if by not in ("time", "measure"):
        raise ImportFailed(path, _BAD_BY)
    if by == "measure":
        _check_reference(document, reference, path)
    if timeline.kind == "harmony" and not harmony_available():
        raise ImportFailed(path, _HARMONY_NEEDS)
    if by == "measure":
        raise NotImplementedError("Importing by measure isn't possible yet")
    return _BY_TIME[timeline.kind](document, target, path)


def harmony_available() -> bool:
    """Whether music21 can be imported, which the `harmony` extra installs. It is
    looked for, not imported."""
    return importlib.util.find_spec("music21") is not None


def _check_reference(document: tla.Document, reference: str | None, path: Path) -> None:
    if reference is None:
        raise ImportFailed(path, _NO_REFERENCE)
    timeline = _timeline(document, reference, path)
    if timeline.kind != "beat":
        raise ImportFailed(path, _NOT_A_BEAT_TIMELINE.format(_named(timeline)))


def _timeline(document: tla.Document, timeline_id: str, path: Path) -> tla.Timeline:
    try:
        return document.timelines[timeline_id]
    except KeyError:
        raise ImportFailed(path, _NO_TIMELINE.format(timeline_id)) from None


def _named(timeline: tla.Timeline) -> str:
    """How a refusal names a timeline: `Beat timeline 'Measures' (ordinal 2)`. A name
    is optional, an ordinal isn't, and a kind the core doesn't know is given as the
    file spells it, capitalised."""
    kind = timeline.kind
    spelling = kind.spelling if isinstance(kind, tla.UnknownKind) else kind
    text = f"{spelling[:1].upper()}{spelling[1:]} timeline".lstrip()
    if timeline.name:
        text += f" '{timeline.name}'"
    return f"{text} (ordinal {timeline.ordinal})"
