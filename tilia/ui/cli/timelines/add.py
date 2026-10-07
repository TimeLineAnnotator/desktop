import argparse

import tilia.errors
from tilia.requests import Get, get
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.beat.pattern import parse
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.timelines.range.timeline import RangeTimeline
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.ui.cli import io
from tilia.ui.cli.io import output
from tilia.ui.timelines.beat_time_signatures import get_creation_args


def setup_parser(subparser):
    add_subp = subparser.add_parser(
        "add",
        exit_on_error=False,
        help="Add a new timeline",
        epilog="""
Examples:
  timelines add beat --name "Measures" --beat-pattern 4
  timelines add beat --name "Measures" --beat-pattern 10[4] 3 15[4]
  timelines add hierarchy --name "Form"
  timelines add marker --name "Cadences"
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_subp.add_argument(
        "kind",
        choices=[
            "hierarchy",
            "hrc",
            "marker",
            "mrk",
            "beat",
            "bea",
            "score",
            "sco",
            "range",
            "rng",
        ],
        help="Kind of timeline to add",
    )
    add_subp.add_argument(
        "--name", "-n", type=str, default="", help="Name of the new timeline"
    )
    add_subp.add_argument(
        "--height", "-e", type=int, default=None, help="Height of the timeline"
    )
    add_subp.add_argument(
        "--beat-pattern",
        "-b",
        type=str,
        nargs="+",
        default=None,
        help="Beats per measure, separated by spaces (beat timelines only). "
        "The pattern repeats after its last measure: '3 4' alternates measures "
        "of 3 and 4 beats. Use n[...] to repeat a group: '10[4] 3' is ten "
        "measures of 4, then one of 3. Defaults to 4.",
    )
    add_subp.add_argument(
        "--row-height",
        dest="default_row_height",
        type=int,
        default=None,
        help="Per-timeline default row height (range timelines only). "
        "Defaults to the global setting.",
    )
    add_subp.set_defaults(func=add)


TLKIND_TO_KWARGS_NAMES = {
    BeatTimeline: ["name", "height", "beat_pattern"],
    HierarchyTimeline: ["name", "height"],
    MarkerTimeline: ["name", "height"],
    RangeTimeline: ["name", "height", "default_row_height"],
    ScoreTimeline: ["name", "height"],
}

# arg attr -> (timeline kind it's valid for, flag name for the error message)
KIND_SPECIFIC_ARGS = {
    "beat_pattern": (BeatTimeline, "--beat-pattern"),
    "default_row_height": (RangeTimeline, "--row-height"),
}


def get_kwargs_by_timeline_type(namespace: argparse.Namespace, kind: type[Timeline]):
    kwargs = {}
    for attr in TLKIND_TO_KWARGS_NAMES[kind]:
        kwargs[attr] = getattr(namespace, attr)
    return kwargs


def add(namespace: argparse.Namespace):
    KIND_STR_TO_TLKIND = {
        "hierarchy": HierarchyTimeline,
        "hrc": HierarchyTimeline,
        "marker": MarkerTimeline,
        "mrk": MarkerTimeline,
        "beat": BeatTimeline,
        "bea": BeatTimeline,
        "score": ScoreTimeline,
        "sco": ScoreTimeline,
        "range": RangeTimeline,
        "rng": RangeTimeline,
    }

    if not get(Get.MEDIA_DURATION):
        tilia.errors.display(tilia.errors.CLI_CREATE_TIMELINE_WITHOUT_DURATION)
        return
    kind = namespace.kind
    name = namespace.name

    tl_type = KIND_STR_TO_TLKIND[kind]

    for attr, (expected_kind, flag) in KIND_SPECIFIC_ARGS.items():
        if getattr(namespace, attr) is not None and tl_type is not expected_kind:
            tilia.errors.display(
                tilia.errors.CLI_ADD_TIMELINE_ARG_NOT_APPLICABLE, flag, kind
            )
            return

    kwargs = get_kwargs_by_timeline_type(namespace, tl_type)
    if kwargs.get("beat_pattern") is not None:
        pattern = " ".join(kwargs["beat_pattern"])
        result = parse(pattern)
        if not result.is_complete:
            io.error(f"Invalid beat pattern '{pattern}': {result.error}")
            return
        kwargs["beat_pattern"] = pattern
    if tl_type is BeatTimeline:
        kwargs |= get_creation_args(kwargs.get("height"))

    output(f"Adding timeline with {kind=}, {name=}")

    get(Get.TIMELINE_COLLECTION).create_timeline(tl_type, **kwargs)
