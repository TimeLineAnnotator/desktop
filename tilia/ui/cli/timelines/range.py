from __future__ import annotations

import argparse
from functools import wraps
from typing import Callable

from tilia.requests import Get, get
from tilia.timelines.range.timeline import RangeTimeline
from tilia.ui.cli import io
from tilia.ui.cli.timelines.utils import (
    get_timeline_by_name,
    get_timeline_by_ordinal,
)


def setup_parser(subparser):
    range_parser = subparser.add_parser(
        "range",
        exit_on_error=False,
        help="Range timeline operations.",
    )
    range_subp = range_parser.add_subparsers(dest="range_command", required=True)

    _setup_row_parser(range_subp)


def _setup_row_parser(subparser):
    row_parser = subparser.add_parser(
        "row",
        exit_on_error=False,
        help="Range timeline row operations.",
    )
    row_subp = row_parser.add_subparsers(dest="row_command", required=True)

    _setup_add(row_subp)
    _setup_set_height(row_subp)
    _setup_list(row_subp)
    _setup_rename(row_subp)
    _setup_set_color(row_subp)
    _setup_reset_color(row_subp)
    _setup_reorder(row_subp)
    _setup_remove(row_subp)


def _add_target_args(parser: argparse.ArgumentParser) -> None:
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        "--tl-ordinal", "-o", type=int, help="Target range timeline ordinal"
    )
    target_group.add_argument(
        "--tl-name", "-n", type=str, help="Target range timeline name"
    )


def _add_row_selector_args(parser: argparse.ArgumentParser) -> None:
    row_group = parser.add_mutually_exclusive_group(required=True)
    row_group.add_argument(
        "--row-index", type=int, help="Index of the target row (0-based)"
    )
    row_group.add_argument("--row-name", type=str, help="Name of the target row")


def _setup_add(subparser):
    parser = subparser.add_parser(
        "add",
        exit_on_error=False,
        help="Add a row to a range timeline. Out-of-bound indices are clamped.",
    )
    _add_target_args(parser)
    parser.add_argument("--name", type=str, default=None, help="Name of the new row")
    parser.add_argument("--color", type=str, default=None, help="Color of the new row")
    parser.add_argument(
        "--index",
        type=int,
        default=None,
        help="Index at which to insert the row (default: append).",
    )
    parser.set_defaults(func=add_row)


def _setup_set_height(subparser):
    parser = subparser.add_parser(
        "set-height",
        exit_on_error=False,
        help="Set the row height for a range timeline.",
    )
    _add_target_args(parser)
    parser.add_argument(
        "--height", type=int, required=True, help="New row height (>= 10)"
    )
    parser.set_defaults(func=set_row_height)


def _setup_list(subparser):
    parser = subparser.add_parser(
        "list",
        exit_on_error=False,
        help="List the rows of a range timeline.",
    )
    _add_target_args(parser)
    parser.set_defaults(func=list_rows)


def _setup_rename(subparser):
    parser = subparser.add_parser(
        "rename",
        exit_on_error=False,
        help="Rename a row in a range timeline.",
    )
    _add_target_args(parser)
    _add_row_selector_args(parser)
    parser.add_argument(
        "--new-name", type=str, required=True, help="New name for the row"
    )
    parser.set_defaults(func=rename_row)


def _setup_set_color(subparser):
    parser = subparser.add_parser(
        "set-color",
        exit_on_error=False,
        help="Set the color of a row in a range timeline.",
    )
    _add_target_args(parser)
    _add_row_selector_args(parser)
    parser.add_argument(
        "--color", type=str, required=True, help="Hex color (e.g. #ff0000)"
    )
    parser.set_defaults(func=set_row_color)


def _setup_reset_color(subparser):
    parser = subparser.add_parser(
        "reset-color",
        exit_on_error=False,
        help="Clear a row's color so it falls back to the default setting.",
    )
    _add_target_args(parser)
    _add_row_selector_args(parser)
    parser.set_defaults(func=reset_row_color)


def _setup_reorder(subparser):
    parser = subparser.add_parser(
        "reorder",
        exit_on_error=False,
        help="Move a row to a new position. Out-of-bound indices are clamped.",
    )
    _add_target_args(parser)
    _add_row_selector_args(parser)
    parser.add_argument(
        "--new-index",
        type=int,
        required=True,
        help="Target index for the row (0-based).",
    )
    parser.set_defaults(func=reorder_row)


def _setup_remove(subparser):
    parser = subparser.add_parser(
        "remove",
        exit_on_error=False,
        help="Remove a row (and any ranges on it) from a range timeline.",
    )
    _add_target_args(parser)
    _add_row_selector_args(parser)
    parser.set_defaults(func=remove_row)


def _resolve_timeline(namespace: argparse.Namespace) -> RangeTimeline | None:
    if namespace.tl_ordinal is not None:
        success, tl = get_timeline_by_ordinal(namespace.tl_ordinal)
    else:
        success, tl = get_timeline_by_name(namespace.tl_name)
    if not success or tl is None:
        return None
    if not isinstance(tl, RangeTimeline):
        io.error(f"Timeline {tl} is not a range timeline.")
        return None
    return tl


def _resolve_row(timeline: RangeTimeline, namespace: argparse.Namespace):
    if namespace.row_index is not None:
        row = timeline.get_row_by_index(namespace.row_index)
        if row is None:
            io.error(
                f"No row at index {namespace.row_index} (timeline has "
                f"{timeline.row_count} row(s))."
            )
        return row

    matches = [r for r in timeline.rows if r.name == namespace.row_name]
    if not matches:
        io.error(f"No row named '{namespace.row_name}' in timeline.")
        return None
    if len(matches) > 1:
        io.warn(f"Multiple rows named '{namespace.row_name}' — operating on the first.")
    return matches[0]


def with_timeline(func: Callable) -> Callable:
    """Resolve --tl-ordinal/--tl-name to a RangeTimeline; abort on failure.

    Wrapped functions take (timeline, namespace) instead of (namespace).
    """

    @wraps(func)
    def wrapper(namespace: argparse.Namespace) -> None:
        timeline = _resolve_timeline(namespace)
        if timeline is None:
            return
        func(timeline, namespace)

    return wrapper


def with_row(func: Callable) -> Callable:
    """Resolve --row-index/--row-name to a Row on the already-resolved
    timeline. Stacks under @with_timeline.

    Wrapped functions take (timeline, row, namespace).
    """

    @wraps(func)
    def wrapper(timeline: RangeTimeline, namespace: argparse.Namespace) -> None:
        row = _resolve_row(timeline, namespace)
        if row is None:
            return
        func(timeline, row, namespace)

    return wrapper


@with_timeline
def add_row(timeline: RangeTimeline, namespace: argparse.Namespace) -> None:
    idx = namespace.index
    if idx is not None:
        clamped = max(0, min(idx, timeline.row_count))
        if clamped != idx:
            io.warn(
                f"Index {idx} out of bounds; clamped to {clamped} "
                f"(timeline has {timeline.row_count} row(s))."
            )
        idx = clamped

    timeline.add_row(name=namespace.name, color=namespace.color, idx=idx)


@with_timeline
def set_row_height(timeline: RangeTimeline, namespace: argparse.Namespace) -> None:
    get(Get.TIMELINE_COLLECTION).set_timeline_data(
        timeline.id, "default_row_height", namespace.height
    )


@with_timeline
def list_rows(timeline: RangeTimeline, namespace: argparse.Namespace) -> None:
    if not timeline.rows:
        io.output(f"Timeline {timeline.name!r} has no rows.")
        return
    headers = ["index", "name", "color", "ranges"]
    data = []
    for idx, row in enumerate(timeline.rows):
        ranges = len(timeline.get_ranges_by_row(row.id))
        data.append((str(idx), row.name, row.color or "(default)", str(ranges)))
    io.tabulate(headers, data, title=f"Rows in {timeline.name!r}")


@with_timeline
@with_row
def rename_row(timeline: RangeTimeline, row, namespace: argparse.Namespace) -> None:
    timeline.rename_row(row, namespace.new_name)


@with_timeline
@with_row
def set_row_color(timeline: RangeTimeline, row, namespace: argparse.Namespace) -> None:
    timeline.set_row_color(row, namespace.color)


@with_timeline
@with_row
def reset_row_color(
    timeline: RangeTimeline, row, namespace: argparse.Namespace
) -> None:
    timeline.reset_row_color(row)


@with_timeline
@with_row
def reorder_row(timeline: RangeTimeline, row, namespace: argparse.Namespace) -> None:
    new_index = namespace.new_index
    clamped = max(0, min(new_index, timeline.row_count - 1))
    if clamped != new_index:
        io.warn(
            f"Index {new_index} out of bounds; clamped to {clamped} "
            f"(timeline has {timeline.row_count} row(s))."
        )

    timeline.reorder_row(row, clamped)


@with_timeline
@with_row
def remove_row(timeline: RangeTimeline, row, namespace: argparse.Namespace) -> None:
    if timeline.row_count <= 1:
        io.error("Cannot remove the last row of a range timeline.")
        return
    timeline.remove_row(row)
