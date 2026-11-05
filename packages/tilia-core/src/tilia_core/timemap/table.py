"""A beat timeline's measure table: each measure's position, pass, movement,
start and end, meter and time signature, and its start and length in quarter
notes. A measure ends at the next downbeat, or at the closing tap that closes
it, and the last one otherwise at a closing barline worked out from the beats."""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any, NoReturn

from tilia_core import tla
from tilia_core.timemap._rows import RowIn, _is_number, closing_taps, rows_of
from tilia_core.timemap.meters import meters_of
from tilia_core.timemap.qstamps import beat_lengths
from tilia_core.timemap.units import MeasureMeter, format_units

# Float noise: two beats closer than this are at the same time, and a time this
# much beyond the tolerance is still on a beat.
EPS = 1e-6


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
        """Refused: a measure's metadata is read-only."""
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
    end: float  # the next downbeat, or the closing barline: a closing tap, if `closed`
    beat_ids: tuple[str, ...]
    beats: int  # the beats tapped
    meter: MeasureMeter  # desktop#621's, from the beat units in effect
    qstamp: Fraction  # its downbeat's position in quarter notes, from the first beat
    # Computed from the meter, so nothing can make them disagree with it:
    time_signature: str = field(init=False)  # "6/8", "2+2+3/8", "(4/3)/4"
    ts_numerator: Fraction = field(init=False)  # the beat values' sum, however grouped
    ts_denominator: int = field(init=False)
    assumed: bool = field(init=False)  # nobody set the unit that governs it
    ambiguous: bool = field(init=False)  # the taps don't hold whole patterns
    conflicting: bool = field(init=False)  # more than one unit is set on its beats
    quarters: Fraction = field(init=False)  # how long it lasts in quarter notes
    source: str
    force_display: bool
    next: tuple[str, ...] | None
    metadata: FrozenMetadata
    closed: bool = False  # a closing tap ends it, the tap in no row's `beat_ids`

    def __post_init__(self) -> None:
        meter = self.meter
        numerator = meter.numerator
        computed = {
            "time_signature": format_time_signature(
                meter.beat_values, meter.denominator
            ),
            "ts_numerator": numerator,
            "ts_denominator": meter.denominator,
            "assumed": meter.is_assumed,
            "ambiguous": meter.is_ambiguous,
            "conflicting": meter.is_conflicting,
            # The sum of its beats' lengths, as its time signature's numerator
            # is the sum of their values.
            "quarters": meter.quarter_length(numerator),
        }
        for name, value in computed.items():
            object.__setattr__(self, name, value)


def build_rows(document: tla.Document, timeline: tla.Timeline) -> list[MeasureRow]:
    """The timeline's measure table, in its order; also for a folded table.

    No rows while the table has a problem (`table_problem` says which): rows
    built then would be wrong, with measures that end before they start.
    """
    if table_problem(timeline) is not None:
        return []
    return build_rows_from(document, timeline, rows_of(timeline))


def table_problem(timeline: tla.Timeline) -> str | None:
    """Why the timeline's table can't give rows, as a reason; else None.

    A beat without a usable time (`missing_time`), a row whose beats don't
    start at its downbeat or aren't the timeline's (`broken_row`), or two
    beats at the same time or out of time order (`disorder`). A beat without
    a usable time is found among the timeline's beats, so a timeline without
    a table, or with an empty one, can have that problem too; it has no other.
    None doesn't promise rows: such a timeline has none, with no problem.
    """
    return _checked(timeline)[0]


def _checked(timeline: tla.Timeline) -> tuple[str | None, list[float]]:
    # The table's problem, and the times of its beats in its order: none when it
    # has a problem, so the times given are always usable. A closing tap is in no
    # row, but two taps at one time are still two beats at the same time.
    reason = missing_time(timeline) or broken_row(timeline)
    if reason is not None:
        return reason, []
    times = _times(timeline)
    reason = disorder(times) or disorder(
        sorted([*times, *(tap.time for tap in closing_taps(timeline))])
    )
    return reason, [] if reason is not None else times


def _times(timeline: tla.Timeline) -> list[float]:
    # The times of the table's beats, in its order, once broken_row has found
    # each of them a beat of the timeline, and missing_time each beat's time
    # usable.
    rows = timeline.measures.rows if timeline.measures is not None else []
    return [timeline.components[b].attrs["time"] for row in rows for b in row.beats]


def disorder(times: Sequence[float]) -> str | None:
    """The first two beats at the same time, or the first out of time order, as
    a reason; else None."""
    for a, b in itertools.pairwise(times):
        if abs(b - a) < EPS:
            return f"two beats at the same time ({a})"
        if b < a:
            return f"beats out of time order (at {b})"
    return None


def media_warning(document: tla.Document, timeline: tla.Timeline) -> str | None:
    """The warning, with the timeline's id, that its last beat is at or after
    the end of the media; None when it isn't, or when the table has no rows.

    With more than one beat, the last beat lasts its own length at the tempo
    of the gap before it, and the warning says the last measure ends one gap
    after it; with one, it ends on the beat. A last measure that a closing tap
    closes ends at the tap, and `closing_warnings` speaks for that.
    """
    reason, times = _checked(timeline)
    if reason is not None or not times or _last_row_is_closed(timeline):
        return None
    last, gap = _last_gap(times)
    media_length = _media_length(document)
    if media_length is None or not _ends_by(media_length, last):
        return None
    warning = (
        f"Timeline {timeline.id}: the last beat ({last}) is at or after "
        f"the end of the media ({media_length})"
    )
    if gap > 0:
        warning += "; the last measure ends one gap after it"
    return warning


def closing_warnings(document: tla.Document, timeline: tla.Timeline) -> list[str]:
    """The warnings, with the timeline's id and the beat's, about its closing
    taps, in time order: one for each read as an ordinary beat, and one for
    each closing barline past the end of the media, where it is kept (FR-011).
    None when the table has no rows."""
    reason, times = _checked(timeline)
    if reason is not None or not times:
        return []
    media_length = _media_length(document)
    warnings: list[str] = []
    for tap in closing_taps(timeline):
        if not tap.barline:
            warnings.append(
                f"Timeline {timeline.id}: beat {tap.id} is marked closing, but "
                "isn't the last tap of the timeline or of a movement; it is read "
                "as an ordinary beat"
            )
        elif media_length is not None and tap.time > media_length:
            warnings.append(
                f"Timeline {timeline.id}: the closing tap {tap.id} ({tap.time}) is "
                f"past the end of the media ({media_length})"
            )
    return warnings


def _last_row_is_closed(timeline: tla.Timeline) -> bool:
    last = timeline.measures.rows[-1].id  # _checked has found beats in rows
    return any(tap.barline and tap.row == last for tap in closing_taps(timeline))


def missing_time(timeline: tla.Timeline) -> str | None:
    """The first of the timeline's beats without a usable time, as a reason
    naming it by its id; else None.

    A time is usable when it is a finite number: a missing, NaN or text time
    isn't, nor a whole number too large for a float. The timeline's beats are
    looked at, not its rows: WP3's table leaves a beat without a time out of
    every row, since its measure is found by its time. So the reason names
    no measure (TimeLineAnnotator/project-management#381), and of several
    such beats, the first by id, as a file lists them. A beat with a
    `measure` mark is a downbeat, but for a closing tap, whose mark starts no
    measure (TimeLineAnnotator/project-management#375).
    """
    timeless = [
        beat_id
        for beat_id, component in timeline.components.items()
        if component.kind == "beat" and not _is_number(component.attrs.get("time"))
    ]
    if not timeless:
        return None
    first = min(timeless)
    attrs = timeline.components[first].attrs
    downbeat = isinstance(attrs.get("measure"), dict) and not attrs.get("closing")
    what = "a downbeat" if downbeat else "a beat"
    return f"{what} without a time (beat {first})"


def broken_row(timeline: tla.Timeline) -> str | None:
    """The first row whose beats don't start at its downbeat, or that names a
    beat the timeline doesn't have, as a reason; else None.

    Only a broken table has one: WP3 builds each row from the timeline's
    beats, from its downbeat on.
    """
    if timeline.measures is None:
        return None
    for measure in timeline.measures.rows:
        if (
            not measure.beats
            or measure.beats[0] != measure.id
            or not all(_is_beat(timeline, beat_id) for beat_id in measure.beats)
        ):
            return (
                f"the measure table doesn't match its beats (measure {measure.label})"
            )
    return None


def _is_beat(timeline: tla.Timeline, component_id: str) -> bool:
    component = timeline.components.get(component_id)
    return component is not None and component.kind == "beat"


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
    meters = meters_of(rows)
    ends = [
        following.beat_times[0] if row.closing is None else row.closing
        for row, following in itertools.pairwise(rows)
    ]
    ends.append(_closing_barline(document, rows, meters))
    passes: dict[int, int] = {}
    movement = 1
    qstamp = Fraction(0)
    out: list[MeasureRow] = []
    for index, (row, end, meter) in enumerate(zip(rows, ends, meters, strict=True)):
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
                meter=meter,
                qstamp=qstamp,
                source=row.source,
                force_display=row.force_display,
                next=row.next,
                metadata=FrozenMetadata(row.metadata),
                closed=row.closing is not None,
            )
        )
        qstamp += out[-1].quarters
    return out


def format_time_signature(beat_values: Sequence[Fraction], denominator: int) -> str:
    """A measure's time signature as a musician reads it.

    The numerator is the sum of the beat values when they are all equal ("6/8"),
    and the values joined by "+" when they differ, as they fall in the measure
    ("2+2+3/8"; three taps under 2+3 give "2+3+2/8"). A numerator that isn't
    whole, or holds a fraction, is in brackets: "(4/3)/4", "(1/2+1)/8".
    """
    if len(set(beat_values)) > 1:
        parts = list(beat_values)
    else:
        parts = [sum(beat_values, Fraction(0))]
    numerator = format_units(parts)
    if any(part.denominator != 1 for part in parts):
        numerator = f"({numerator})"
    return f"{numerator}/{denominator}"


def is_folded(rows: Sequence[RowIn]) -> bool:
    """Whether the table lists the measures played next: a score in written order."""
    return any(row.next is not None for row in rows)


def _closing_barline(
    document: tla.Document, rows: Sequence[RowIn], meters: Sequence[MeasureMeter]
) -> float:
    # A closing tap is the closing barline, wherever the media ends (FR-011).
    # Else the last beat lasts its own length at the tempo of the gap before
    # it, or until the end of the media if that comes sooner: the tempo at
    # which the time map's quarter notes go on past it (FR-011, FR-051). When
    # the last two beats are worth the same, that is the gap itself. No beats
    # are added to the last measure.
    if rows[-1].closing is not None:
        return rows[-1].closing
    last, gap = _last_gap([t for row in rows[-2:] for t in row.beat_times])
    if len(rows) > 1 and len(rows[-1].beat_times) == 1 and rows[-2].closing is not None:
        # A pause isn't a gap, as it holds no quarter notes: the gap before the
        # last beat is the one its movement's closing tap ended.
        gap = rows[-2].closing - rows[-2].beat_times[-1]
    lengths = [length for meter in meters[-2:] for length in beat_lengths(meter)]
    if len(lengths) > 1:
        gap *= float(lengths[-1] / lengths[-2])
    end = last + gap
    media_length = _media_length(document)
    if media_length is None or _ends_by(media_length, last):
        return end  # past the media, that length alone; find_time_map warns
    return min(end, media_length)


def _last_gap(times: Sequence[float]) -> tuple[float, float]:
    # The last beat, and the gap before it, which the last measure lasts past
    # it: none for a single beat. The closing barline and its warning share it.
    return times[-1], (times[-1] - times[-2] if len(times) > 1 else 0.0)


def _media_length(document: tla.Document) -> float | None:
    """The media's length, when it caps the closing barline; else None.

    It is in seconds, so it doesn't cap a quarters file. The format allows a
    number above zero, or none. Since desktop#744 the reader refuses text and
    bools, and a file can't hold NaN or infinity, so a file can give only zero
    or less, or a whole number too large for a float, beside what it allows.
    Those count as none, and so does anything else a document made in memory
    holds.
    """
    length: object = document.media_length
    if document.time_unit != "seconds" or not _is_number(length):
        return None
    return length if length > 0 else None


def _ends_by(media_length: float, last_beat: float) -> bool:
    # Whether the media ends at or before the last beat: one test for the
    # closing barline and its warning, so they can't disagree.
    return media_length <= last_beat


def find_rows(
    rows: Sequence[MeasureRow],
    number: int | None = None,
    *,
    label: str | None = None,
    pass_: int | None = None,
    movement: int | None = None,
) -> list[MeasureRow]:
    """The rows a bar names: by number (every pass, cadenzas left out), by label
    (cadenzas included), or both; `pass_` narrows them to one time through, and
    `movement` to one movement, else every movement matches.
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
        and (movement is None or row.movement == movement)
    ]
