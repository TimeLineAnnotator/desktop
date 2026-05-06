from __future__ import annotations

from pathlib import Path
from typing import Any

from tilia.parsers.csv.base import (
    TiliaCSVReader,
    get_column_not_found_error_message,
    get_params_indices,
)
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.range.components import Range
from tilia.timelines.range.timeline import RangeTimeline


def _get_or_create_row(timeline: RangeTimeline, row_name: str) -> RangeTimeline.Row:
    for row in timeline.rows:
        if row.name == row_name:
            return row
    return timeline.add_row(name=row_name)


_TRUE_LITERALS = {"true", "1", "yes", "y", "t"}
_FALSE_LITERALS = {"false", "0", "no", "n", "f", ""}


def _parse_optional_bool(value: str) -> tuple[bool, bool]:
    """Parse a permissive boolean. Returns (ok, value) — `ok=False` signals
    an unrecognised input the caller should report as a CSV error."""
    s = value.strip().lower()
    if s in _FALSE_LITERALS:
        return True, False
    if s in _TRUE_LITERALS:
        return True, True
    return False, False


def _apply_pending_joins(
    timeline: RangeTimeline,
    pending_joins: list[tuple[Range, str, bool]],
) -> list[str]:
    """`pending_joins` is a list of `(range_obj, row_id, joined_flag)`. For
    each entry with `joined_flag=True`, point its `joined_right` at the
    *temporally* next range on the same row (sorted by start time, not CSV
    order — the CSV makes no ordering promise).

    Returns error messages for invalid configurations: a flagged range with
    no next neighbor on its row, or a flagged range whose end doesn't line
    up exactly with the next range's start (which would violate the
    `r1.end == r2.start` invariant of joins). The ranges themselves are
    left in place — only the offending join is dropped."""
    errors: list[str] = []
    by_row: dict[str, list[tuple[Range, bool]]] = {}
    for rng, row_id, flag in pending_joins:
        by_row.setdefault(row_id, []).append((rng, flag))

    for row_id, entries in by_row.items():
        entries.sort(key=lambda e: e[0])
        row = timeline.get_row_by_id(row_id)
        row_label = row.name if row is not None else row_id
        for i, (rng, flag) in enumerate(entries):
            if not flag:
                continue
            if i + 1 >= len(entries):
                errors.append(
                    f"start={rng.start}, end={rng.end} | "
                    f"joined_with_next=true on last range of row "
                    f"{row_label!r}; no next neighbor to join with"
                )
                continue
            target = entries[i + 1][0]
            if rng.end != target.start:
                errors.append(
                    f"start={rng.start}, end={rng.end} | "
                    f"joined_with_next=true but next range on row "
                    f"{row_label!r} starts at {target.start} (must equal "
                    f"{rng.end} for ranges to join)"
                )
                continue
            timeline.set_component_data(rng.id, "joined_right", target.id)
    return errors


def import_by_time(
    timeline: RangeTimeline,
    path: Path,
    file_kwargs: dict[str, Any] | None = None,
    reader_kwargs: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """
    Create ranges in a timeline from a csv file with start/end times.
    Assumes the first row of the file contains headers.
    Header names should match range properties; 'start', 'end' and 'row'
    are required, others are optional. Rows referenced in the 'row' column
    are auto-created on the timeline by name.
    Returns (success, error_messages).
    """

    errors: list[str] = []
    pending_joins: list[tuple[Range, str, bool]] = []

    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        header = next(reader)
        params_to_indices = get_params_indices(
            [
                "start",
                "end",
                "row",
                "label",
                "color",
                "comments",
                "joined_with_next",
            ],
            header,
        )

        for required in ("start", "end", "row"):
            if required not in params_to_indices:
                return False, [get_column_not_found_error_message(required)]

        for csv_row in reader:
            if not csv_row:
                continue

            try:
                start = float(csv_row[params_to_indices["start"]])
            except ValueError:
                bad = csv_row[params_to_indices["start"]]
                errors.append(f"start={bad!r} | {bad} is not a valid time")
                continue

            try:
                end = float(csv_row[params_to_indices["end"]])
            except ValueError:
                bad = csv_row[params_to_indices["end"]]
                errors.append(f"end={bad!r} | {bad} is not a valid time")
                continue

            row_name = csv_row[params_to_indices["row"]]
            if not row_name:
                errors.append(
                    f"start={start}, end={end} | row name is empty; skipping."
                )
                continue
            row = _get_or_create_row(timeline, row_name)

            joined_flag = False
            if "joined_with_next" in params_to_indices:
                raw = csv_row[params_to_indices["joined_with_next"]]
                ok, joined_flag = _parse_optional_bool(raw)
                if not ok:
                    errors.append(
                        f"start={start}, end={end} | "
                        f"joined_with_next={raw!r} is not a valid boolean"
                    )
                    joined_flag = False

            kwargs: dict[str, Any] = {
                "start": start,
                "end": end,
                "row_id": row.id,
            }
            for opt in ("label", "color", "comments"):
                if opt in params_to_indices:
                    value = csv_row[params_to_indices[opt]]
                    if opt == "color" and not value:
                        continue
                    kwargs[opt] = value

            component, fail_reason = timeline.create_component(
                ComponentKind.RANGE, **kwargs
            )
            if not component:
                errors.append(fail_reason)
                continue
            pending_joins.append((component, row.id, joined_flag))

        errors.extend(_apply_pending_joins(timeline, pending_joins))
        return True, errors


def import_by_measure(
    timeline: RangeTimeline,
    beat_tl: BeatTimeline,
    path: Path,
    file_kwargs: dict[str, Any] | None = None,
    reader_kwargs: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """
    Create ranges in a timeline from a csv file with 1-based measure indices.
    Required columns: 'start', 'end', 'row'. Optional: 'start_fraction',
    'end_fraction', 'label', 'color', 'comments'. Rows referenced by name
    are auto-created on the timeline.
    Returns (success, error_messages).
    """

    errors: list[str] = []
    pending_joins: list[tuple[Range, str, bool]] = []

    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        header = next(reader)

        required = [("start", int), ("end", int), ("row", str)]
        optional = [
            ("start_fraction", float),
            ("end_fraction", float),
            ("label", str),
            ("color", str),
            ("comments", str),
            ("joined_with_next", str),
        ]

        params_to_indices = get_params_indices([p[0] for p in required], header)
        params_to_indices.update(get_params_indices([p[0] for p in optional], header))

        for attr, _ in required:
            if attr not in params_to_indices:
                return False, [get_column_not_found_error_message(attr)]

        for csv_row in reader:
            if not csv_row:
                continue

            try:
                start_measure = int(csv_row[params_to_indices["start"]])
                end_measure = int(csv_row[params_to_indices["end"]])
            except ValueError:
                bad = csv_row[params_to_indices["start"]]
                errors.append(f"{bad} is not a valid measure number")
                continue

            row_name = csv_row[params_to_indices["row"]]
            if not row_name:
                errors.append(
                    f"start={start_measure}, end={end_measure} | "
                    "row name is empty; skipping."
                )
                continue

            fractions = {"start": 0.0, "end": 0.0}
            for ext in fractions:
                attr = f"{ext}_fraction"
                if attr in params_to_indices:
                    fraction_value = csv_row[params_to_indices[attr]]
                    try:
                        fractions[ext] = float(fraction_value)
                    except ValueError:
                        errors.append(
                            f"start={start_measure}, end={end_measure} | "
                            f"{fraction_value} is not a fraction value. "
                            "Defaulting to 0."
                        )

            start_times = beat_tl.get_time_by_measure(start_measure, fractions["start"])
            end_times = beat_tl.get_time_by_measure(end_measure, fractions["end"], True)

            if not start_times:
                errors.append(
                    f"start={start_measure} | No measure with number "
                    f"{start_measure}"
                )
                continue
            if not end_times:
                errors.append(
                    f"end={end_measure} | No measure with number {end_measure}"
                )
                continue

            kwargs: dict[str, Any] = {}
            for param, parser in optional:
                if param in ("start_fraction", "end_fraction", "joined_with_next"):
                    continue
                if param in params_to_indices:
                    value = csv_row[params_to_indices[param]]
                    if param == "color" and not value:
                        continue
                    try:
                        kwargs[param] = parser(value)
                    except ValueError:
                        errors.append(
                            f"start={start_measure}, end={end_measure} | "
                            f"'{value}' is not a valid {param} value."
                        )

            joined_flag = False
            if "joined_with_next" in params_to_indices:
                raw = csv_row[params_to_indices["joined_with_next"]]
                ok, joined_flag = _parse_optional_bool(raw)
                if not ok:
                    errors.append(
                        f"start={start_measure}, end={end_measure} | "
                        f"joined_with_next={raw!r} is not a valid boolean"
                    )
                    joined_flag = False

            row = _get_or_create_row(timeline, row_name)

            # Mirror the hierarchy parser's "pair start/end" logic so repeated
            # measure numbers map to multiple distinct ranges.
            start_pool = start_times.copy()
            end_pool = end_times.copy()
            csv_row_components: list[Range] = []
            while start_pool and end_pool:
                start = start_pool[0]
                end = end_pool[0]
                if start < end:
                    component, fail_reason = timeline.create_component(
                        ComponentKind.RANGE,
                        start=start,
                        end=end,
                        row_id=row.id,
                        **kwargs,
                    )
                    if not component:
                        errors.append(fail_reason)
                    else:
                        csv_row_components.append(component)
                    start_pool.pop(0)
                    end_pool.pop(0)
                    continue
                while end_pool and start_pool[0] >= end_pool[0]:
                    end_pool.pop(0)

            # joined_with_next is interpreted at the CSV-row level: only the
            # last range produced by this row gets the flag. Earlier ranges
            # (from repeated measure numbers) stay unjoined.
            for i, component in enumerate(csv_row_components):
                last = i == len(csv_row_components) - 1
                pending_joins.append((component, row.id, joined_flag and last))

        errors.extend(_apply_pending_joins(timeline, pending_joins))
        return True, errors
