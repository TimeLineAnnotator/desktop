from __future__ import annotations

import argparse
from collections.abc import Callable
from functools import wraps

from tilia.requests import Get, get
from tilia.timelines.beat.pattern import parse
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.beat.units import parse_units
from tilia.ui.cli import io
from tilia.ui.cli.timelines.utils import (
    get_timeline_by_name,
    get_timeline_by_ordinal,
)
from tilia.ui.consts import BEAT_TIMELINE_TIME_SIGNATURE_BAND_HEIGHT
from tilia.ui.format import format_numerator


def setup_parser(subparser):
    beat_parser = subparser.add_parser(
        "beat",
        exit_on_error=False,
        help="Beat timeline operations.",
    )
    beat_subp = beat_parser.add_subparsers(dest="beat_command", required=True)

    _setup_pattern_parser(beat_subp)
    _setup_unit_parser(beat_subp)
    _setup_time_signatures_parser(beat_subp)


def _setup_pattern_parser(subparser):
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


def _setup_pattern_set(subparser):
    parser = subparser.add_parser(
        "set",
        exit_on_error=False,
        help="Set the beat pattern and recompute every measure from it.",
        epilog="""
Examples:
  timelines beat pattern set -o 1 4
  timelines beat pattern set -o 1 10[4] 3 15[4]
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_target_args(parser)
    parser.add_argument(
        "pattern",
        type=str,
        nargs="+",
        help="Beats per measure, separated by spaces. Use n[...] to repeat a group.",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Overwrite measures set by hand without asking.",
    )
    parser.set_defaults(func=set_pattern)


def _setup_unit_parser(subparser):
    unit_parser = subparser.add_parser(
        "unit",
        exit_on_error=False,
        help="Beat unit operations: what one tapped beat is worth in notation.",
    )
    unit_subp = unit_parser.add_subparsers(dest="unit_command", required=True)

    parser = unit_subp.add_parser(
        "set",
        exit_on_error=False,
        help="Set the beat unit of a measure.",
        epilog="""
Examples:
  timelines beat unit set -o 1 --measure 12 --denominator 8 --units 3
  timelines beat unit set -o 1 --measure 5 -d 4 -u 2+3 --scope measure
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _add_target_args(parser)
    _add_measure_args(parser)
    parser.add_argument(
        "--denominator", "-d", type=int, required=True, help="Denominator"
    )
    parser.add_argument(
        "--units",
        "-u",
        type=str,
        required=True,
        help="Units per tap, '+'-separated whole numbers or fractions "
        "(e.g. 1, 3, 2+3, 1/2).",
    )
    parser.add_argument(
        "--scope",
        choices=["onward", "measure"],
        default="onward",
        help="Apply until the next change (default) or to this measure only.",
    )
    parser.set_defaults(func=set_unit)

    parser = unit_subp.add_parser(
        "remove",
        exit_on_error=False,
        help="Remove the beat unit that starts at a measure.",
    )
    _add_target_args(parser)
    _add_measure_args(parser)
    parser.set_defaults(func=remove_unit)

    parser = unit_subp.add_parser(
        "list",
        exit_on_error=False,
        help="List the beat units of a beat timeline.",
    )
    _add_target_args(parser)
    parser.set_defaults(func=list_units)


def _setup_time_signatures_parser(subparser):
    parser = subparser.add_parser(
        "time-signatures",
        exit_on_error=False,
        help="Show or hide the time signatures of a beat timeline.",
    )
    parser.add_argument("action", choices=["show", "hide"])
    _add_target_args(parser)
    parser.set_defaults(func=set_time_signatures_visibility)


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
def set_unit(timeline: BeatTimeline, namespace: argparse.Namespace) -> None:
    measure_index = _resolve_measure(timeline, namespace)
    if measure_index is None:
        return
    result = parse_units(namespace.units)
    if not result.is_valid:
        io.error(f"Invalid units '{namespace.units}': {result.error}")
        return
    if namespace.denominator < 1:
        io.error(f"Invalid denominator: {namespace.denominator}.")
        return

    timeline.set_beat_unit(
        measure_index,
        namespace.denominator,
        namespace.units,
        only_this_measure=namespace.scope == "measure",
    )


@with_timeline
def remove_unit(timeline: BeatTimeline, namespace: argparse.Namespace) -> None:
    measure_index = _resolve_measure(timeline, namespace)
    if measure_index is None:
        return
    meter = timeline.get_measure_meter(measure_index)
    if not meter.starts_here:
        io.error("No beat unit starts at that measure.")
        return
    timeline.delete_components([timeline.get_component(meter.beat_unit_id)])


@with_timeline
def list_units(timeline: BeatTimeline, namespace: argparse.Namespace) -> None:
    beat_units = timeline.beat_units
    if not beat_units:
        io.output(f"Timeline {timeline.name!r} has no beat units.")
        return

    headers = ["measure", "beat time", "denominator", "units", "time signature"]
    data = []
    for beat_unit in beat_units:
        beat = timeline.get_component(beat_unit.beat_id)
        measure_index, _ = timeline.get_measure_index(timeline.get_beat_index(beat))
        numerator, denominator = timeline.get_measure_meter(
            measure_index
        ).time_signature
        time_signature = f"{format_numerator(numerator)}/{denominator}"
        if beat_unit.assumed:
            time_signature += " (assumed)"
        data.append(
            (
                str(timeline.measure_numbers[measure_index]),
                str(beat.time),
                str(beat_unit.denominator),
                beat_unit.units,
                time_signature,
            )
        )
    io.tabulate(headers, data, title=f"Beat units in {timeline.name!r}")


@with_timeline
def set_time_signatures_visibility(
    timeline: BeatTimeline, namespace: argparse.Namespace
) -> None:
    show = namespace.action == "show"
    if show == timeline.show_time_signatures:
        return
    collection = get(Get.TIMELINE_COLLECTION)
    height_change = BEAT_TIMELINE_TIME_SIGNATURE_BAND_HEIGHT
    if not show:
        height_change = -height_change
    collection.set_timeline_data(timeline.id, "show_time_signatures", show)
    collection.set_timeline_data(timeline.id, "height", timeline.height + height_change)
