"""Time signatures from a source or an edit, as a plan of beat-unit writes.

A plan lists basic writes, each with its old and new value, which a caller
can preview, apply in memory (`apply_plan`) and undo. Writing files is WP3's
writer's: nothing here opens one.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from fractions import Fraction
from typing import Any

from tilia_core import tla
from tilia_core.timemap._rows import RowIn, _beat_unit, _dict, rows_of
from tilia_core.timemap.meters import meters_of
from tilia_core.timemap.table import (
    MeasureRow,
    build_rows,
    build_rows_from,
    find_rows,
    format_time_signature,
    table_problem,
)
from tilia_core.timemap.units import (
    MAX_DENOMINATOR,
    MeasureMeter,
    format_units,
    parse_units,
    validate_denominator,
)

# A unit as a measure reads it: its denominator, its units, and whether it is
# assumed.
_Unit = tuple[int, tuple[Fraction, ...], bool]

# What each `source` records on the measures it sets; an edit records
# "edited", unless the measure is "tapped" (WP3's FR-081).
_SOURCES = {"score": "score", "import": "import", "edit": "edited"}
_KEYS = ("beat_unit", "measure.source", "measure_source")
_DIGITS = frozenset("0123456789")
_MISSING = object()  # a component, mark or timeline that a change names and isn't there


@dataclass(frozen=True)
class TimeSignature:
    """A time signature from a source or an edit: one part ("6/8") or a grouping ("2+2+3/8")."""

    parts: tuple[Fraction, ...]
    denominator: int

    def __post_init__(self) -> None:
        # The parts are units, so units.py says which are allowed.
        readable = parse_units(format_units(self.parts))
        if not readable.is_valid:
            raise ValueError(
                f"A time signature's parts must be units: {readable.error}"
            )
        # Text such as "12" is written as "1+2", and reads back as two parts.
        if readable.units != list(self.parts):
            raise ValueError(
                "A time signature's parts must be whole numbers or fractions,"
                f" not {self.parts!r}."
            )
        if not validate_denominator(self.denominator):
            raise ValueError(
                f"A time signature's denominator must be from 1 to {MAX_DENOMINATOR},"
                f" not {self.denominator!r}."
            )
        object.__setattr__(self, "parts", tuple(readable.units))

    @classmethod
    def parse(cls, text: str) -> TimeSignature:
        """Reads what `format_time_signature` writes: "6/8", "2+2+3/8", "(4/3)/4",
        "(1/2+1)/8". A numerator that holds a fraction must be in brackets."""
        numerator, slash, denominator = text.strip().rpartition("/")
        if not slash:
            raise ValueError(f"{text!r} is not a time signature such as 6/8.")
        if numerator.startswith("(") and numerator.endswith(")"):
            numerator = numerator[1:-1]
        elif "/" in numerator:
            raise ValueError(
                f"{text!r}: a numerator that holds a fraction goes in brackets,"
                " as in (4/3)/4."
            )
        parts = parse_units(numerator)
        if not parts.is_valid:
            raise ValueError(f"{text!r} is not a time signature: {parts.error}")
        denominator = denominator.strip()
        if not denominator or not set(denominator) <= _DIGITS:
            raise ValueError(f"{text!r}: the denominator must be a whole number.")
        return cls(tuple(parts.units), int(denominator))


@dataclass(frozen=True)
class BarRef:
    """A bar as a source names it: by printed number or label, every time
    through unless `pass_` narrows it, in every movement unless `movement` does."""

    number: int | None = None
    label: str | None = None
    pass_: int | None = None
    movement: int | None = None


@dataclass(frozen=True)
class Change:
    """One basic write, with the value it expects to replace.

    `key` is "beat_unit" (a beat's unit), "measure.source" (the source in a
    downbeat's mark) or "measure_source" (the timeline's; `component_id` is
    None). None as `old` or `new` means the value is absent.
    """

    timeline_id: str
    component_id: str | None
    key: str
    old: Any
    new: Any


@dataclass(frozen=True)
class Plan:
    """The writes that give some measures their time signatures, in order.

    `unmatched` holds the bars the table doesn't have, and `ambiguous` those
    found in more than one movement with none given: nothing is written for
    either. `basis` is what the plan was made from, by timeline, and
    `apply_plan` refuses the plan once it has changed. A plan made by hand
    has none, and is checked by its changes' old values alone.
    """

    changes: list[Change] = field(default_factory=list)
    unmatched: list[BarRef | str] = field(default_factory=list)
    ambiguous: list[BarRef] = field(default_factory=list)
    basis: dict[str, object] = field(default_factory=dict, compare=False, repr=False)


class PlanOutOfDate(Exception):
    """The document changed since the plan was made.

    `change` is the first change whose old value differs, or None when what
    the plan was made from did.
    """

    def __init__(self, message: str, change: Change | None = None) -> None:
        super().__init__(message)
        self.change = change


def plan_time_signatures(
    document: tla.Document,
    timeline_id: str,
    settings: Sequence[tuple[BarRef | str, TimeSignature]],
    *,
    source: str,
    after: str = "restore",
) -> Plan:
    """
    The writes that give the measures `settings` name their time signatures,
    on the beat timeline `timeline_id`. A setting names its bar with a
    `BarRef` or a downbeat's id; of two settings for one measure, the later
    wins. A bar the table doesn't have goes to `unmatched`, and one found in
    more than one movement, with none given, to `ambiguous`; nothing is
    written for either. A table without rows (a beat without a time, say)
    has none of the bars. In a folded table a pass counts the measures in
    written order (`MeasureRow.folded`). Measures the settings don't name
    get no write but the units `after` writes back.

    Each measure's own taps share its time signature: its unit is the
    numerator divided by the taps, exactly, or the parts of a grouping with a
    part per tap. It goes on the beat of the unit that starts in the measure,
    which is edited, else on the downbeat, and is not assumed. Every measure
    set records `source` ("score", "import", or "edit": "edited", unless the
    measure is tapped); when every measure of the table is set and records
    the same source, the timeline records it instead, changing its
    `measure_source` if need be, and the marks lose their own, even where
    every measure already reads it, through its mark or the timeline. A
    measure whose unit, "assumed" flag and source are already right gets no
    write, unless its mark has its own source and every measure is set.

    `after` says what the measures the settings don't name read afterwards.
    With "restore", the default, each keeps its reading: its unit and its
    "assumed" flag. Where one would read another, the unit it read is written
    back, with that flag, on its downbeat. That is only ever a measure after
    one set, or the first of a movement whose first unit the plan writes
    (FR-020), and the measures after it carry the unit on as before. With
    "carry", nothing more is written, so the measures after a run of set
    measures take its unit, from there on.

    Writes nothing to the document. Raises ValueError for a unit too long to
    be read back.
    """
    if after not in ("restore", "carry"):
        raise ValueError(f"after must be 'restore' or 'carry', not {after!r}.")
    if source not in _SOURCES:
        raise ValueError(f"source must be 'score', 'import' or 'edit', not {source!r}.")
    timeline = document.timelines.get(timeline_id)
    if timeline is None or timeline.kind != "beat":
        raise ValueError(f"{timeline_id!r} is not a beat timeline of the document.")

    # build_rows, keeping the rows as read for _write_backs.
    rows_in = rows_of(timeline) if table_problem(timeline) is None else []
    rows = build_rows_from(document, timeline, rows_in)
    wanted, unmatched, ambiguous = _match(rows, settings)
    restore = after == "restore"
    unit_changes = _unit_changes(timeline, rows, wanted, restore=restore)
    if restore:
        unit_changes.update(_write_backs(timeline, rows, rows_in, wanted, unit_changes))
    timeline_change, mark_changes = _source_changes(timeline, rows, wanted, source)

    changes = [] if timeline_change is None else [timeline_change]
    for row in rows:
        for change in (unit_changes.get(row.id), mark_changes.get(row.id)):
            if change is not None:
                changes.append(change)
    basis = {timeline.id: _basis(timeline, rows)}
    return Plan(changes, unmatched, ambiguous, basis)


def _match(
    rows: Sequence[MeasureRow],
    settings: Sequence[tuple[BarRef | str, TimeSignature]],
) -> tuple[dict[str, TimeSignature], list[BarRef | str], list[BarRef]]:
    """The time signature for each measure set, by downbeat id; the bars not
    found; the bars found in more than one movement, with none given."""
    by_id = {row.id: row for row in rows}
    # find_rows decides what a bar matches; these only narrow what it scans.
    by_number: dict[int, list[MeasureRow]] = {}
    by_label: dict[str, list[MeasureRow]] = {}
    for row in rows:
        by_number.setdefault(row.number, []).append(row)
        by_label.setdefault(row.label, []).append(row)

    wanted: dict[str, TimeSignature] = {}
    unmatched: list[BarRef | str] = []
    ambiguous: list[BarRef] = []
    for bar, time_signature in settings:
        if isinstance(bar, str):
            matches = [by_id[bar]] if bar in by_id else []
        else:
            if bar.number is not None:
                candidates = by_number.get(bar.number, [])
            else:
                candidates = [] if bar.label is None else by_label.get(bar.label, [])
            matches = find_rows(
                candidates, bar.number, label=bar.label, pass_=bar.pass_
            )
            if bar.movement is not None:
                matches = [row for row in matches if row.movement == bar.movement]
            elif len({row.movement for row in matches}) > 1:
                ambiguous.append(bar)
                continue
        if not matches:
            unmatched.append(bar)
        for row in matches:
            wanted[row.id] = time_signature
    return wanted, unmatched, ambiguous


def _unit_changes(
    timeline: tla.Timeline,
    rows: Sequence[MeasureRow],
    wanted: dict[str, TimeSignature],
    *,
    restore: bool,
) -> dict[str, Change]:
    """The beat-unit write each measure set needs, by downbeat id.

    The unit that governs each measure once the writes before it are made is
    followed through the table: where the rules start a unit (one set on the
    measure's beats, or one they supply, as on the first measure), the
    measure's meter gives it; elsewhere it is carried on from the measure
    before. With `restore`, a measure not set keeps its reading
    (`_write_backs`), so its meter gives it too.
    """
    changes: dict[str, Change] = {}
    governing: _Unit | None = None
    for row in rows:
        time_signature = wanted.get(row.id)
        own = _own(row)
        kept = restore and time_signature is None
        if own is not None or row.meter.starts_here or kept:
            governing = _reading(row.meter)
        if time_signature is None:
            continue
        unit = (time_signature.denominator, _units(time_signature, row.beats), False)
        if governing != unit:
            readable = parse_units(format_units(unit[1]))
            if not readable.is_valid:
                written = format_time_signature(
                    time_signature.parts, time_signature.denominator
                )
                raise ValueError(
                    f"Measure {row.label}: {written} over {row.beats} taps"
                    f" gives units that can't be read back: {readable.error}"
                )
            changes[row.id] = _unit_change(timeline, own or row.id, unit)
        governing = unit
    return changes


def _write_backs(
    timeline: tla.Timeline,
    rows: Sequence[MeasureRow],
    rows_in: Sequence[RowIn],
    wanted: dict[str, TimeSignature],
    unit_changes: dict[str, Change],
) -> dict[str, Change]:
    """
    With "restore": the writes that keep every measure not set reading as it
    did, by downbeat id.

    `meters_of` reads the rows again with the units the plan writes. From the
    left, the first measure not set that reads otherwise than it did (its
    unit or its "assumed" flag) gets the unit it read, with that flag, on its
    downbeat, and the rows are read again, until every measure not set reads
    as it did. Such a measure has no unit of its own, which would still
    govern it, so the unit written back is the one that governs it.

    So nothing is written where a measure would read the same anyway
    (TimeLineAnnotator/project-management#356), and a movement's first
    measure is kept as the timeline's first is
    (TimeLineAnnotator/project-management#357, after
    TimeLineAnnotator/project-management#322). A unit that can't be read, on
    the downbeat written to, is replaced
    (TimeLineAnnotator/project-management#373).
    """
    # rows_in and rows are the same measures, in the same order.
    planned = list(rows_in)
    index_of = {row.id: index for index, row in enumerate(rows)}
    for row_id, change in unit_changes.items():
        planned[index_of[row_id]] = _put(planned[index_of[row_id]], change)
    before = [_reading(row.meter) for row in rows]
    write_backs: dict[str, Change] = {}
    while True:
        meters = meters_of(planned)
        # One write-back per measure at most, so that this ends whatever the
        # rules read.
        index = next(
            (
                i
                for i, row in enumerate(rows)
                if row.id not in wanted
                and row.id not in write_backs
                and _reading(meters[i]) != before[i]
            ),
            None,
        )
        if index is None:
            return write_backs
        row_id = rows[index].id
        write_backs[row_id] = _unit_change(timeline, row_id, before[index])
        planned[index] = _put(planned[index], write_backs[row_id])


def _put(row: RowIn, change: Change) -> RowIn:
    """The row with a unit the plan writes among its units, as `rows_of` will
    read it: in the place of the one it edits, or first, on the downbeat."""
    new = change.new
    unit = tla.BeatUnit(
        denominator=new["denominator"],
        units=new["units"],
        assumed=bool(new.get("assumed", False)),
    )
    beat_id = change.component_id or ""
    units = list(row.units)
    for index, (other, _) in enumerate(units):
        if other == beat_id:
            units[index] = (beat_id, unit)
            break
    else:
        units.insert(0, (beat_id, unit))
    return replace(row, units=tuple(units))


def _own(row: MeasureRow) -> str | None:
    """The beat of the unit that starts in the measure, if one does."""
    beat_id = row.meter.beat_unit_id
    return beat_id if beat_id in row.beat_ids else None


def _reading(meter: MeasureMeter) -> _Unit:
    """The unit that governs a measure, as it reads it."""
    return meter.denominator, tuple(meter.units), meter.is_assumed


def _unit_change(timeline: tla.Timeline, beat_id: str, unit: _Unit) -> Change:
    """The write that puts `unit` on the beat, as the format stores it."""
    old = timeline.components[beat_id].attrs.get("beat_unit")
    new: dict[str, Any] = {"denominator": unit[0], "units": format_units(unit[1])}
    if unit[2]:
        new["assumed"] = True
    return Change(timeline.id, beat_id, "beat_unit", copy.deepcopy(old), new)


def _units(time_signature: TimeSignature, taps: int) -> tuple[Fraction, ...]:
    """The units of a measure of `taps` taps that has the time signature."""
    parts = time_signature.parts
    if len(parts) > 1 and len(parts) == taps:
        return parts[:1] if len(set(parts)) == 1 else parts
    return (sum(parts, Fraction(0)) / taps,)


def _source_changes(
    timeline: tla.Timeline,
    rows: Sequence[MeasureRow],
    wanted: dict[str, TimeSignature],
    source: str,
) -> tuple[Change | None, dict[str, Change]]:
    """The change to the timeline's `measure_source`, if any, and the change
    to the source in each set measure's mark, by downbeat id."""
    targets = {row.id: _target(row, source) for row in rows if row.id in wanted}
    table_source = _measure_source(timeline)
    # Every measure set, all from one source: the timeline records it (FR-071),
    # even when every measure already reads it through its own mark, so that
    # the same table gives the same file however many plans built it
    # (TimeLineAnnotator/project-management#340). So this comes before any
    # measure is skipped.
    every = len(targets) == len(rows) and len(set(targets.values())) == 1
    measure_source = next(iter(targets.values())) if every else table_source
    changed = measure_source != table_source
    timeline_change = None
    if changed:
        timeline_change = Change(
            timeline.id, None, "measure_source", table_source, measure_source
        )

    mark_changes: dict[str, Change] = {}
    for row in rows:
        target = targets.get(row.id)
        if target is None:
            continue
        own = _dict(timeline.components.get(row.id), "measure").get("source")
        if every:
            # Every measure now has the timeline's source: a mark's own goes,
            # also a copy of a source the timeline already had
            # (TimeLineAnnotator/project-management#343).
            needed, new = own is not None, None
        else:
            needed = row.source != target
            new = None if target == table_source else target
        if needed:
            mark_changes[row.id] = Change(
                timeline.id, row.id, "measure.source", own, new
            )
    return timeline_change, mark_changes


def _target(row: MeasureRow, source: str) -> str:
    if source == "edit" and row.source == "tapped":
        return "tapped"
    return _SOURCES[source]


def _measure_source(timeline: tla.Timeline) -> str | None:
    """The timeline's own measure source: as stored, else as its table has it."""
    table = timeline.measures
    return timeline.attrs.get("measure_source", None if table is None else table.source)


def _basis(timeline: tla.Timeline, rows: Sequence[MeasureRow]) -> tuple[Any, ...]:
    """What a plan for the timeline is made from: its measure table as
    computed, the sources in its marks, and its own."""
    marks = tuple(
        _dict(timeline.components.get(row.id), "measure").get("source") for row in rows
    )
    return _measure_source(timeline), tuple(rows), marks


def apply_plan(document: tla.Document, plan: Plan) -> None:
    """
    Applies a plan's changes to the document, in memory, in order: the last
    write wins. First, every change's old value is checked against the
    document as the changes before it leave it, then what the plan was made
    from (`Plan.basis`) against the document as it is. If either differs,
    raises `PlanOutOfDate`, naming the change if it is one, and changes nothing.

    A "beat_unit" change sets or removes a beat's `beat_unit`, a
    "measure.source" change the `source` in a downbeat's `measure` mark, a
    "measure_source" change the timeline's. The rows of the timeline's
    measure table follow: their `source`, and the `beat_units` of the
    measures whose beats changed; their `beat_unit`, the unit in force, is
    not updated. Opens no file: WP3's writer writes the document.
    """
    pending: dict[tuple[str, str | None, str], Any] = {}
    for change in plan.changes:
        # The timeline's own source is one value, whatever a change's component.
        component_id = None if change.key == "measure_source" else change.component_id
        place = (change.timeline_id, component_id, change.key)
        current = pending[place] if place in pending else _value(document, change)
        if current is _MISSING or current != change.old:
            found = "missing" if current is _MISSING else repr(current)
            raise PlanOutOfDate(
                "The document changed since the plan was made:"
                f" {change.key} of {change.component_id or change.timeline_id}"
                f" is {found}, not {change.old!r}.",
                change,
            )
        pending[place] = change.new
    for timeline_id, basis in plan.basis.items():
        timeline = document.timelines.get(timeline_id)
        if (
            timeline is None
            or _basis(timeline, build_rows(document, timeline)) != basis
        ):
            raise PlanOutOfDate(
                "The document changed since the plan was made: the measures of"
                f" timeline {timeline_id} aren't those it was made from."
            )

    beats: dict[str, set[str]] = {}
    for change in plan.changes:
        timeline = document.timelines[change.timeline_id]
        _write(timeline, change)
        changed = beats.setdefault(timeline.id, set())
        if change.key == "beat_unit" and change.component_id is not None:
            changed.add(change.component_id)
    for timeline_id, changed in beats.items():
        _update_table(document.timelines[timeline_id], changed)


def _value(document: tla.Document, change: Change) -> Any:
    """The value a change would replace, as the document has it now."""
    if change.key not in _KEYS:
        raise ValueError(f"A plan can't change {change.key!r}.")
    timeline = document.timelines.get(change.timeline_id)
    if timeline is None:
        return _MISSING
    if change.key == "measure_source":
        return _measure_source(timeline)
    component = timeline.components.get(change.component_id or "")
    if component is None:
        return _MISSING
    if change.key == "beat_unit":
        return component.attrs.get("beat_unit")
    mark = component.attrs.get("measure")
    return mark.get("source") if isinstance(mark, dict) else _MISSING


def _write(timeline: tla.Timeline, change: Change) -> None:
    new = copy.deepcopy(change.new)
    if change.key == "measure_source":
        _set(timeline.attrs, "measure_source", new)
        return
    attrs = timeline.components[change.component_id or ""].attrs
    if change.key == "beat_unit":
        _set(attrs, "beat_unit", new)
    else:
        mark = dict(attrs["measure"])
        _set(mark, "source", new)
        attrs["measure"] = mark


def _set(values: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        values.pop(key, None)
    else:
        values[key] = value


def _update_table(timeline: tla.Timeline, changed: set[str]) -> None:
    """Brings the table's rows in line with the marks and the units: their
    sources, and the units of the measures whose beats changed, as the
    measure table reads them."""
    table = timeline.measures
    if table is None:
        return
    table.source = _measure_source(timeline) or table.source
    for row in table.rows:
        own = _dict(timeline.components.get(row.id), "measure").get("source")
        row.source = table.source if own is None else own
        if changed.intersection(row.beats):
            components = (timeline.components.get(b) for b in row.beats)
            units = (_beat_unit(timeline, c) for c in components if c is not None)
            row.beat_units = [unit for unit in units if unit is not None]
