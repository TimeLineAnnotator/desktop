from __future__ import annotations

import argparse
from collections.abc import Callable
from functools import wraps

from tilia.timelines.beat.pattern import parse, parse_time_signature_over_taps
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.ui.cli import io
from tilia.ui.cli.timelines.utils import (
    get_timeline_by_name,
    get_timeline_by_ordinal,
)
from tilia.ui.timelines.beat_bars import format_row, get_rows
from tilia.ui.timelines.beat_time_signatures import set_time_signatures_shown


def setup_parser(subparser: argparse._SubParsersAction) -> None:
    beat_parser = subparser.add_parser(
        "beat",
        exit_on_error=False,
        help="Beat timeline operations.",
    )
    beat_subp = beat_parser.add_subparsers(dest="beat_command", required=True)

    _setup_pattern_parser(beat_subp)
    _setup_time_signatures_parser(beat_subp)


def _setup_pattern_parser(subparser: argparse._SubParsersAction) -> None:
    pattern_parser = subparser.add_parser(
        "pattern",
        exit_on_error=False,
        help="Beat pattern operations.",
    )
    pattern_subp = pattern_parser.add_subparsers(dest="pattern_command", required=True)

    _setup_pattern_set(pattern_subp)


def _add_target_args(parser: argparse.ArgumentParser) -> None:
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        "--tl-ordinal", "-o", type=int, help="Target beat timeline ordinal"
    )
    target_group.add_argument(
        "--tl-name", "-n", type=str, help="Target beat timeline name"
    )


def _setup_pattern_set(subparser: argparse._SubParsersAction) -> None:
    parser = subparser.add_parser(
        "set",
        exit_on_error=False,
        help="Set the time signatures of the bars and recompute every measure "
        "from them.",
        epilog="""
Examples:
  timelines beat pattern set -o 1 4/4
  timelines beat pattern set -o 1 4[4/4] 3/4 3[4/4]
  timelines beat pattern set -o 1 6/8(3 3)
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_target_args(parser)
    parser.add_argument(
        "pattern",
        type=str,
        nargs="+",
        help="Time signatures of the bars, separated by spaces, starting again "
        "from the first after the last. Use n[...] to repeat a group. Taps "
        "default to one per beat; otherwise give their values in brackets, "
        "e.g. 6/8(3 3). A number alone is that many taps of an assumed "
        "quarter note.",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Overwrite measures set by hand without asking.",
    )
    parser.set_defaults(func=set_pattern)


def _setup_time_signatures_parser(subparser: argparse._SubParsersAction) -> None:
    time_signatures_parser = subparser.add_parser(
        "time-signatures",
        exit_on_error=False,
        help="Time signature operations.",
    )
    time_signatures_subp = time_signatures_parser.add_subparsers(
        dest="time_signatures_command", required=True
    )

    parser = time_signatures_subp.add_parser(
        "set",
        exit_on_error=False,
        help="Set the time signature of a measure, over the taps it has.",
        epilog="""
Examples:
  timelines beat time-signatures set -o 1 --measure 12 6/8
  timelines beat time-signatures set -o 1 -m 5 4/4(3/2 3/2 1) --scope measure
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_target_args(parser)
    _add_measure_args(parser)
    parser.add_argument(
        "time_signature",
        type=str,
        nargs="+",
        help="A time signature such as 3/4. The measure keeps its taps, each "
        "worth the same, so 6/8 over two taps is two dotted quarters. To give "
        "the taps other values, put them in brackets: 4/4(3/2 3/2 1).",
    )
    parser.add_argument(
        "--scope",
        choices=["onward", "measure"],
        default="onward",
        help="Apply until the next change (default) or to this measure only.",
    )
    parser.set_defaults(func=set_time_signature)

    parser = time_signatures_subp.add_parser(
        "remove",
        exit_on_error=False,
        help="Remove the time signature change at a measure, so the one "
        "before carries on.",
    )
    _add_target_args(parser)
    _add_measure_args(parser)
    parser.set_defaults(func=remove_time_signature)

    parser = time_signatures_subp.add_parser(
        "list",
        exit_on_error=False,
        help="List the bars of a beat timeline, with their time signatures and "
        "taps.",
    )
    _add_target_args(parser)
    parser.set_defaults(func=list_bars)

    for action in ("show", "hide"):
        parser = time_signatures_subp.add_parser(
            action,
            exit_on_error=False,
            help=f"{action.capitalize()} the time signatures of a beat timeline.",
        )
        _add_target_args(parser)
        parser.set_defaults(func=set_time_signatures_visibility, action=action)


def _add_measure_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--measure",
        "-m",
        type=int,
        help="Measure number as displayed. Refused if it appears more than once.",
    )
    group.add_argument(
        "--measure-index", type=int, help="Position of the measure (0-based)."
    )


def _resolve_measure(
    timeline: BeatTimeline, namespace: argparse.Namespace
) -> int | None:
    if namespace.measure_index is not None:
        if 0 <= namespace.measure_index < timeline.measure_count:
            return namespace.measure_index
        io.error(
            f"No measure at index {namespace.measure_index} (timeline has "
            f"{timeline.measure_count} measure(s))."
        )
        return None

    matches = [
        i
        for i, number in enumerate(timeline.measure_numbers)
        if number == namespace.measure
    ]
    if not matches:
        io.error(f"No measure numbered {namespace.measure}.")
        return None
    if len(matches) > 1:
        io.error(
            f"Measure number {namespace.measure} appears more than once "
            f"(indices {', '.join(map(str, matches))}). Use --measure-index."
        )
        return None
    return matches[0]


def _resolve_timeline(namespace: argparse.Namespace) -> BeatTimeline | None:
    if namespace.tl_ordinal is not None:
        success, tl = get_timeline_by_ordinal(namespace.tl_ordinal)
    else:
        success, tl = get_timeline_by_name(namespace.tl_name)
    if not success or tl is None:
        return None
    if not isinstance(tl, BeatTimeline):
        io.error(f"Timeline {tl} is not a beat timeline.")
        return None
    return tl


def with_timeline(func: Callable) -> Callable:
    """Resolve --tl-ordinal/--tl-name to a BeatTimeline; abort on failure.

    Wrapped functions take (timeline, namespace) instead of (namespace).
    """

    @wraps(func)
    def wrapper(namespace: argparse.Namespace) -> None:
        timeline = _resolve_timeline(namespace)
        if timeline is None:
            return
        func(timeline, namespace)

    return wrapper


@with_timeline
def set_pattern(timeline: BeatTimeline, namespace: argparse.Namespace) -> None:
    pattern = " ".join(namespace.pattern)
    result = parse(pattern)
    if not result.is_complete:
        io.error(f"Invalid beat pattern '{pattern}': {result.error}")
        return

    overwritten = timeline.get_bars_overwritten_by(result.bars)
    if overwritten and not namespace.yes:
        measures = ", ".join(str(i + 1) for i in overwritten)
        if not io.ask_yes_or_no(
            f"This pattern will overwrite measures set by hand (measures "
            f"{measures}). Continue?",
            default=False,
        ):
            return

    timeline.set_beat_pattern(pattern)


@with_timeline
def set_time_signature(timeline: BeatTimeline, namespace: argparse.Namespace) -> None:
    measure_index = _resolve_measure(timeline, namespace)
    if measure_index is None:
        return
    text = " ".join(namespace.time_signature)
    beat_count = timeline.beats_in_measure[measure_index]
    bar, error = parse_time_signature_over_taps(text, beat_count)
    if bar is not None and bar.beat_count != beat_count:
        error = f"It gives {bar.beat_count} taps, but the measure has {beat_count}."
    if bar is None or error:
        io.error(f"Invalid time signature '{text}': {error}")
        return

    timeline.set_beat_unit(
        measure_index,
        bar.denominator,
        bar.units_text,
        only_this_measure=namespace.scope == "measure",
    )


@with_timeline
def remove_time_signature(
    timeline: BeatTimeline, namespace: argparse.Namespace
) -> None:
    measure_index = _resolve_measure(timeline, namespace)
    if measure_index is None:
        return
    meter = timeline.get_measure_meter(measure_index)
    if not meter.starts_here:
        io.error("The time signature doesn't change at that measure.")
        return
    timeline.delete_components([timeline.get_beat_unit_on_beat(meter.beat_unit_id)])


@with_timeline
def list_bars(timeline: BeatTimeline, namespace: argparse.Namespace) -> None:
    if not len(timeline):
        io.output(f"Timeline {timeline.name!r} has no bars.")
        return

    bars = timeline.get_measures_as_planned_bars()
    rows = get_rows(bars, len(bars), timeline.measure_numbers)
    io.tabulate(
        ["bars", "time signature", "taps"],
        [format_row(row) for row in rows],
        title=f"Bars of {timeline.name!r} (pattern: {timeline.beat_pattern})",
    )


@with_timeline
def set_time_signatures_visibility(
    timeline: BeatTimeline, namespace: argparse.Namespace
) -> None:
    set_time_signatures_shown(timeline.id, namespace.action == "show")
