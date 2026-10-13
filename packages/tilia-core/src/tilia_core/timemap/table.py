"""A beat timeline's measure table: each measure's position, pass, movement, start and end."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, NoReturn

from tilia_core import tla
from tilia_core.timemap._rows import RowIn, rows_of


class FrozenMetadata(dict[str, "str | tuple[str, ...]"]):
    """A measure's metadata, read-only, with its lists as tuples.

    A copy, so a row doesn't follow later edits to the document, and nobody can
    change a time map that others share through it. A dict, so it turns into
    JSON; it hashes, pickles with any protocol, and copies.
    """

    __slots__ = ()

    def __init__(
        self, items: Mapping[str, Any] | Iterable[tuple[str, Any]] = ()
    ) -> None:
        super().__init__(
            (key, tuple(value) if isinstance(value, list) else value)
            for key, value in dict(items).items()
        )

    def _read_only(self, *args: object, **kwargs: object) -> NoReturn:
        raise TypeError("a measure's metadata is read-only")

    __setitem__ = __delitem__ = __ior__ = _read_only  # type: ignore[assignment]
    clear = pop = popitem = setdefault = update = _read_only  # type: ignore[assignment]

    def __hash__(self) -> int:  # type: ignore[override]
        return hash(frozenset(self.items()))

    def __reduce__(self) -> tuple[type[FrozenMetadata], tuple[dict[str, Any]]]:
        return type(self), (dict(self),)

    def __copy__(self) -> FrozenMetadata:
        return self

    def __deepcopy__(self, memo: dict[int, object]) -> FrozenMetadata:
        return self

    def __repr__(self) -> str:
        return f"{type(self).__name__}({dict(self)!r})"


@dataclass(frozen=True)
class MeasureRow:
    """One measure of a beat timeline, with what is computed from the table and never stored."""

    id: str  # its downbeat's id
    count: int  # its row's position in the table, 1…n
    number: int
    label: str
    pass_: int | None  # the times through its number so far; None for a cadenza
    movement: int  # 1, plus one per restart at or before it, but for one on the first row
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
    metadata: FrozenMetadata


def build_rows(document: tla.Document, timeline: tla.Timeline) -> list[MeasureRow]:
    """The timeline's measure table, in its order; also for a folded table.

    None while a beat has no usable time (`missing_time` says which), or while a
    row's beats don't start at its downbeat (`broken_row`): rows built without
    them would be wrong.
    """
    if missing_time(timeline) is not None or broken_row(timeline) is not None:
        return []
    return build_rows_from(document, timeline, rows_of(timeline))


def missing_time(timeline: tla.Timeline) -> str | None:
    """The first beat without a usable time, as a reason naming its measure; else None.

    A time is usable when it is a finite number: a missing, NaN or text time isn't.
    """
    if timeline.measures is None:
        return None
    for measure in timeline.measures.rows:
        for beat_id in (measure.id, *measure.beats):
            if not _has_time(timeline.components.get(beat_id)):
                what = "a downbeat" if beat_id == measure.id else "a beat"
                return f"{what} without a time (measure {measure.label})"
    return None


def broken_row(timeline: tla.Timeline) -> str | None:
    """The first row whose beats don't start at its downbeat, as a reason; else None.

    Only a broken table has one: WP3 builds each row from its downbeat on.
    """
    if timeline.measures is None:
        return None
    for measure in timeline.measures.rows:
        if not measure.beats or measure.beats[0] != measure.id:
            return (
                f"the measure table doesn't match its beats (measure {measure.label})"
            )
    return None


def _has_time(component: tla.Component | None) -> bool:
    time = component.attrs.get("time") if component is not None else None
    return (
        isinstance(time, (int, float))
        and not isinstance(time, bool)
        and math.isfinite(time)
    )


def build_rows_from(
    document: tla.Document, timeline: tla.Timeline, rows: Sequence[RowIn]
) -> list[MeasureRow]:
    """`build_rows` for rows already read from the timeline.

    `rows_of` has kept every row of the table: `build_rows` and `build_time_map`
    give nothing for a table where it wouldn't. So a row's index + 1 is its
    position in WP3's table.
    """
    if not rows:
        return []
    folded = is_folded(rows)
    ends = [row.beat_times[0] for row in rows[1:]]
    ends.append(_closing_barline(document, rows))
    passes: dict[int, int] = {}
    movement = 1
    out: list[MeasureRow] = []
    for index, (row, end) in enumerate(zip(rows, ends, strict=True)):
        count = index + 1
        if row.restart and count > 1:  # the first row is in movement 1 anyway
            passes.clear()
            movement += 1
        pass_: int | None = None
        if not row.cadenza:
            pass_ = passes[row.number] = passes.get(row.number, 0) + 1
        out.append(
            MeasureRow(
                id=row.id,
                count=count,
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
                metadata=FrozenMetadata(row.metadata),
            )
        )
    return out


def is_folded(rows: Sequence[RowIn]) -> bool:
    """Whether the table lists the measures played next: a score in written order."""
    return any(row.next is not None for row in rows)


def _closing_barline(document: tla.Document, rows: Sequence[RowIn]) -> float:
    # The last beat lasts as long as the gap before it, or until the end of the
    # media if that comes sooner. No beats are added to the last measure.
    *before, last = [t for row in rows[-2:] for t in row.beat_times][-2:]
    end = last + (last - before[0] if before else 0.0)
    media_length = _media_length(document)
    if media_length is None or media_length <= last:
        return end  # past the media, the gap alone; find_time_map warns (past_media)
    return min(end, media_length)


def past_media(document: tla.Document, last_beat: float) -> str | None:
    """The warning that the last beat is at or after the end of the media, so
    that the last measure ends one gap after it; None when it isn't."""
    media_length = _media_length(document)
    if media_length is None or media_length > last_beat:
        return None
    return (
        f"the last beat ({last_beat}) is at or after the end of the media "
        f"({media_length}); the last measure ends one gap after it"
    )


def _media_length(document: tla.Document) -> float | None:
    # The media's length is in seconds: it doesn't cap a quarters file.
    return document.media_length if document.time_unit == "seconds" else None


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
