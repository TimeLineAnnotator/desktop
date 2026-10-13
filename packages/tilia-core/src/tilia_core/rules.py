"""TiLiA's rules for creating a component of each kind the importers create.

Each rule gives `(True, "")`, or `(False, reason)` with TiLiA's reason, word for
word, so that the core and TiLiA refuse the same rows in the same words. The
rules are those of `validate_creation` in TiLiA's point-like and segment-like
components, and of `_validate_component_creation` in its timelines.
"""

from __future__ import annotations

from collections.abc import Collection, Hashable

Rule = tuple[bool, str]

_OK: Rule = (True, "")

# The names TiLiA's reasons give each point kind (its components' `frontend_name`).
_POINT_NAMES = {
    "marker": "marker",
    "harmony": "harmony",
    "mode": "mode",
    "beat": "beat",
    "pdf_marker": "PDF page marker",
}


def point(
    time: float, media_length: float, existing_times: Collection[float], *, kind: str
) -> Rule:
    """A marker, harmony, mode, beat or PDF marker (`kind`) at `time`.

    The time must be from 0 to the media length, and no other component of the
    same kind may have it: `existing_times` are theirs.
    """
    if time > media_length:
        return (
            False,
            f"Time '{_media_time(time)}' is bigger than media time"
            f" '{_media_time(media_length)}'",
        )
    if time < 0:
        return False, f"Time can't be negative. Got '{_media_time(time)}'"
    if time in existing_times:
        return (
            False,
            f"There is already a {_POINT_NAMES[kind]} component at the selected position.",
        )
    return _OK


def segment(
    start: float,
    end: float,
    position: Hashable,
    existing_positions: Collection[Hashable],
    media_length: float,
) -> Rule:
    """A hierarchy from `start` to `end`, at `position`: its `(start, end, level)`.

    The start and the end must not be beyond the media length, the end must be
    after the start, and no other hierarchy may have the same position.
    """
    start, end, media_length = float(start), float(end), float(media_length)
    if start > media_length:
        return False, f"Start time '{start}' is bigger than media time '{media_length}'"
    if end > media_length:
        return False, f"End time '{end}' is bigger than media time '{media_length}'"
    if end <= start:
        return False, f"End time '{end}' should be bigger than start time '{start}'"
    if position in existing_positions:
        return (
            False,
            "There is already a hierarchy component at the selected position.",
        )
    return _OK


def range_(
    start: float,
    end: float,
    row_id: str | None,
    row_ids: Collection[str],
    pre_start: float | None,
    post_end: float | None,
    media_length: float,
) -> Rule:
    """A range from `start` to `end` in the row `row_id`, one of `row_ids`.

    `pre_start` and `post_end` are checked when given.
    """
    if not row_id or row_id not in row_ids:
        return False, "Invalid row ID."
    if start >= end:
        return False, "Start time must be before end time."
    if start < 0 or end > media_length:
        return False, "Range is outside media bounds."
    if pre_start is not None and pre_start < 0:
        return False, "pre_start is outside media bounds."
    if post_end is not None and post_end > media_length:
        return False, "post_end is outside media bounds."
    return _OK


def page(page_number: int, page_total: int) -> Rule:
    """A PDF marker's page: one the PDF has, from 1 to `page_total`."""
    if not 1 <= page_number <= page_total:
        return False, "The PDF has no page with that number."
    return _OK


def _media_time(seconds: float) -> str:
    """A time as TiLiA's `format_media_time` writes it: "01:05.0", "1:02:05.0"."""
    seconds_and_fraction = f"{seconds % 60:.1f}".zfill(4)
    minutes = int(float(seconds) // 60)
    hours = f"{minutes // 60}:" if minutes >= 60 else ""
    return f"{hours}{str(minutes % 60).zfill(2)}:{seconds_and_fraction}"
