"""Time signatures from a source or an edit, as a plan of beat-unit writes.

A plan lists basic writes, each with its old and new value, which a caller
can preview, apply in memory (`apply_plan`) and undo. Writing files is WP3's
writer's: nothing here opens one.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Any

from tilia_core import tla
from tilia_core.timemap.table import MeasureRow, build_rows, find_rows
from tilia_core.timemap.units import (
    MAX_DENOMINATOR,
    format_units,
    parse_units,
    validate_denominator,
)

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
        parts = tuple(Fraction(part) for part in self.parts)
        if not parts or any(part <= 0 for part in parts):
            raise ValueError(
                f"A time signature's parts must be greater than 0, not {self.parts!r}."
            )
        if not validate_denominator(self.denominator):
            raise ValueError(
                f"A time signature's denominator must be from 1 to {MAX_DENOMINATOR},"
                f" not {self.denominator!r}."
            )
        object.__setattr__(self, "parts", parts)

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
    found in more than one movement with none given: nothing is written for either.
    """

    changes: list[Change] = field(default_factory=list)
    unmatched: list[BarRef | str] = field(default_factory=list)
    ambiguous: list[BarRef] = field(default_factory=list)


class PlanOutOfDate(Exception):
    """A change's old value no longer matches the document: it changed since the plan was made."""

    def __init__(self, change: Change, current: Any) -> None:
        where = change.component_id or change.timeline_id
        found = "missing" if current is _MISSING else repr(current)
        super().__init__(
            f"The document changed since the plan was made: {change.key} of {where}"
            f" is {found}, not {change.old!r}."
        )
        self.change = change


def plan_time_signatures(
    document: tla.Document,
    timeline_id: str,
    settings: Sequence[tuple[BarRef | str, TimeSignature]],
    *,
    source: str,
    after: str,
) -> Plan:
    """
    The writes that give the measures `settings` name their time signatures,
    on the beat timeline `timeline_id`. A setting names its bar with a
    `BarRef` or a downbeat's id; of two settings for one measure, the later
    wins. A bar the table doesn't have goes to `unmatched`, and one found in
    more than one movement, with none given, to `ambiguous`; nothing is
    written for either. A table without rows (a beat without a time, say)
    has none of the bars. Measures the settings don't name are never written.

    Each measure's own taps share its time signature: its unit is the
    numerator divided by the taps, exactly, or the parts of a grouping with a
    part per tap. It goes on the beat of the unit that starts in the measure,
    which is edited, else on the downbeat, and is not assumed. Every measure
    set records `source` ("score", "import", or "edit": "edited", unless the
    measure is tapped); when every measure of the table would end with the
    same source, the timeline's `measure_source` changes instead, and the
    marks of the measures set lose their own. A measure whose unit, "assumed"
    flag and source are already right gets no write.

    `after` says what the measures after a run of set measures get: "carry",
    the new unit, so nothing more is written. Writes nothing to the document.
    """
    if after == "restore":
        raise ValueError(
            "after='restore' is not available yet: it waits for"
            " TimeLineAnnotator/project-management#194. Use after='carry'."
        )
    if after != "carry":
        raise ValueError(f"after must be 'carry' or 'restore', not {after!r}.")
    if source not in _SOURCES:
        raise ValueError(f"source must be 'score', 'import' or 'edit', not {source!r}.")
    timeline = document.timelines.get(timeline_id)
    if timeline is None or timeline.kind != "beat":
        raise ValueError(f"{timeline_id!r} is not a beat timeline of the document.")

    rows = build_rows(document, timeline)
    wanted, unmatched, ambiguous = _match(rows, settings)
    unit_changes = _unit_changes(timeline, rows, wanted)
    timeline_change, mark_changes = _source_changes(timeline, rows, wanted, source)

    changes = [] if timeline_change is None else [timeline_change]
    for row in rows:
        for change in (unit_changes.get(row.id), mark_changes.get(row.id)):
            if change is not None:
                changes.append(change)
    return Plan(changes, unmatched, ambiguous)


def _match(
    rows: Sequence[MeasureRow],
    settings: Sequence[tuple[BarRef | str, TimeSignature]],
) -> tuple[dict[str, TimeSignature], list[BarRef | str], list[BarRef]]:
    """The time signature for each measure set, by downbeat id; the bars not
    found; the bars found in more than one movement, with none given."""
    by_id = {row.id: row for row in rows}
    wanted: dict[str, TimeSignature] = {}
    unmatched: list[BarRef | str] = []
    ambiguous: list[BarRef] = []
    for bar, time_signature in settings:
        if isinstance(bar, str):
            matches = [by_id[bar]] if bar in by_id else []
        else:
            matches = find_rows(rows, bar.number, label=bar.label, pass_=bar.pass_)
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
) -> dict[str, Change]:
    """The beat-unit write each measure set needs, by downbeat id.

    The unit that governs each measure once the writes before it are made is
    followed through the table: where the rules start a unit (one set on the
    measure's beats, or one they supply, as on the first measure), the
    measure's meter gives it; elsewhere it is carried on from the measure before.
    """
    changes: dict[str, Change] = {}
    governing: tuple[int, tuple[Fraction, ...], bool] | None = None
    for row in rows:
        meter = row.meter
        own = meter.beat_unit_id if meter.beat_unit_id in row.beat_ids else None
        if own is not None or meter.starts_here:
            governing = (meter.denominator, tuple(meter.units), meter.is_assumed)
        time_signature = wanted.get(row.id)
        if time_signature is None:
            continue
        unit = (time_signature.denominator, _units(time_signature, row.beats), False)
        if governing != unit:
            beat_id = own or row.id
            old = timeline.components[beat_id].attrs.get("beat_unit")
            new = {"denominator": unit[0], "units": format_units(unit[1])}
            changes[row.id] = Change(
                timeline.id, beat_id, "beat_unit", copy.deepcopy(old), new
            )
        governing = unit
    return changes


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
    to the source in each set measure's mark, by downbeat id.

    A measure not set is never written: when the timeline's source changes,
    such a measure already has it, in its own mark, which keeps it.
    """
    table = timeline.measures
    targets = {row.id: _target(row, source) for row in rows if row.id in wanted}
    if table is None or all(
        row.source == targets[row.id] for row in rows if row.id in targets
    ):
        return None, {}

    table_source = table.source
    finals = {targets.get(row.id, row.source) for row in rows}
    measure_source = next(iter(finals)) if len(finals) == 1 else table_source
    changed = measure_source != table_source
    timeline_change = None
    if changed:
        old = timeline.attrs.get("measure_source")
        timeline_change = Change(
            timeline.id, None, "measure_source", old, measure_source
        )

    mark_changes: dict[str, Change] = {}
    for row in rows:
        target = targets.get(row.id)
        if target is None:
            continue
        own = _mark(timeline.components.get(row.id)).get("source")
        if changed:
            # Every measure now has the timeline's source: a mark's own goes.
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


def _mark(component: tla.Component | None) -> dict[str, Any]:
    mark = component.attrs.get("measure") if component is not None else None
    return mark if isinstance(mark, dict) else {}


def apply_plan(document: tla.Document, plan: Plan) -> None:
    """
    Applies a plan's changes to the document, in memory, in order: the last
    write wins. Every change's old value is checked first, against the
    document as the changes before it leave it; if one differs, raises
    `PlanOutOfDate` naming it, and changes nothing.

    A "beat_unit" change sets or removes a beat's `beat_unit`, a
    "measure.source" change the `source` in a downbeat's `measure` mark, a
    "measure_source" change the timeline's. The rows of the timeline's
    measure table follow: their sources, and the beat units of the measures
    whose beats changed. Opens no file: WP3's writer writes the document.
    """
    pending: dict[tuple[str, str | None, str], Any] = {}
    for change in plan.changes:
        place = (change.timeline_id, change.component_id, change.key)
        current = pending[place] if place in pending else _value(document, change)
        if current is _MISSING or current != change.old:
            raise PlanOutOfDate(change, current)
        pending[place] = change.new

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
        return timeline.attrs.get("measure_source")
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
    """Brings the measure table's rows in line with the marks and the units."""
    table = timeline.measures
    if table is None:
        return
    table.source = timeline.attrs.get("measure_source", table.source)
    for row in table.rows:
        own = _mark(timeline.components.get(row.id)).get("source")
        row.source = table.source if own is None else own
        if changed.intersection(row.beats):
            units = (_beat_unit(timeline.components.get(b)) for b in row.beats)
            row.beat_units = [unit for unit in units if unit is not None]


def _beat_unit(component: tla.Component | None) -> tla.BeatUnit | None:
    value = component.attrs.get("beat_unit") if component is not None else None
    if not isinstance(value, dict) or not {"denominator", "units"} <= value.keys():
        return None
    return tla.BeatUnit(
        denominator=value["denominator"],
        units=value["units"],
        assumed=bool(value.get("assumed", False)),
    )
