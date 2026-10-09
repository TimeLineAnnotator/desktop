"""A beat timeline's measure table: each measure's position, pass, movement, start and end."""

from __future__ import annotations

import copy
import logging
from collections.abc import Sequence
from dataclasses import dataclass

from tilia_core import tla
from tilia_core.timemap._rows import RowIn, rows_of

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MeasureRow:
    """One measure of a beat timeline, with what is computed from the table and never stored."""

    id: str  # its downbeat's id
    count: int  # its position in the timeline, 1…n
    number: int
    label: str
    pass_: int | None  # the times through its number so far; None for a cadenza
    movement: int  # 1, plus one per restart at or before it
    cadenza: bool
    restart: bool
    folded: bool  # the table has `next`: `count` and `pass_` aren't playing positions
    start: float  # its downbeat
    end: float  # the next downbeat, or the closing barline
    beat_ids: tuple[str, ...]
    beats: int  # the beats tapped
    source: str
    force_display: bool
    next: tuple[str, ...] | None
    metadata: dict[str, str | list[str]]


def build_rows(document: tla.Document, timeline: tla.Timeline) -> list[MeasureRow]:
    """The timeline's measure table, in its order; also for a folded table."""
    return build_rows_from(document, timeline.id, rows_of(timeline))


def build_rows_from(
    document: tla.Document, timeline_id: str, rows: Sequence[RowIn]
) -> list[MeasureRow]:
    """`build_rows` for rows already read from the timeline."""
    if not rows:
        return []
    folded = any(row.next is not None for row in rows)
    ends = [row.beat_times[0] for row in rows[1:]]
    ends.append(_closing_barline(document, timeline_id, rows))
    passes: dict[int, int] = {}
    movement = 1
    out: list[MeasureRow] = []
    for index, (row, end) in enumerate(zip(rows, ends, strict=True)):
        if row.restart:
            passes.clear()
            movement += 1
        pass_: int | None = None
        if not row.cadenza:
            pass_ = passes[row.number] = passes.get(row.number, 0) + 1
        out.append(
            MeasureRow(
                id=row.id,
                count=index + 1,
                number=row.number,
                label=row.label,
                pass_=pass_,
                movement=movement,
                cadenza=row.cadenza,
                restart=row.restart,
                folded=folded,
                start=row.beat_times[0],
                end=end,
                beat_ids=row.beat_ids,
                beats=len(row.beat_ids),
                source=row.source,
                force_display=row.force_display,
                next=row.next,
                metadata=copy.deepcopy(row.metadata),  # not the document's own
            )
        )
    return out


def _closing_barline(
    document: tla.Document, timeline_id: str, rows: Sequence[RowIn]
) -> float:
    # The last beat lasts as long as the gap before it, or until the end of the
    # media if that comes sooner. No beats are added to the last measure.
    *before, last = [t for row in rows[-2:] for t in row.beat_times][-2:]
    end = last + (last - before[0] if before else 0.0)
    media_length = document.media_length
    if media_length is None or document.time_unit != "seconds":
        return end  # the media's length is in seconds
    if media_length <= last:
        logger.warning(
            "Timeline %s: the last beat (%s) is at or after the end of the media (%s); "
            "the last measure ends one gap after it.",
            timeline_id,
            last,
            media_length,
        )
        return end
    return min(end, media_length)


def find_rows(
    rows: Sequence[MeasureRow],
    number: int | None = None,
    *,
    label: str | None = None,
    pass_: int | None = None,
) -> list[MeasureRow]:
    """The rows a bar names: by number (every pass, cadenzas left out), by label
    (cadenzas included), or both; `pass_` narrows them to one time through.
    Nothing, when neither a number nor a label is given."""
    if number is None and label is None:
        return []
    return [
        row
        for row in rows
        if (number is None or row.number == number)
        and (label is None or row.label == label)
        and (label is not None or not row.cadenza)
        and (pass_ is None or row.pass_ == pass_)
    ]
