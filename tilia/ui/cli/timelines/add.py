import argparse

import tilia.errors
from tilia.requests import Get, get
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.timelines.range.timeline import RangeTimeline
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.ui.cli.io import output

# Every kind the user can create, with its abbreviation. SliderTimeline is
# deliberately absent: it comes with the file and can't be deleted.
KIND_STR_TO_TIMELINE_CLASS: dict[str, type[Timeline]] = {
    "beat": BeatTimeline,
    "bea": BeatTimeline,
    "hierarchy": HierarchyTimeline,
    "hrc": HierarchyTimeline,
    "marker": MarkerTimeline,
    "mrk": MarkerTimeline,
    "range": RangeTimeline,
    "rng": RangeTimeline,
    "score": ScoreTimeline,
    "sco": ScoreTimeline,
}

# The creation kwargs each kind accepts. This doubles as the validation
# table: an optional argument the user passed that isn't listed for their
# kind is rejected rather than silently dropped.
TIMELINE_CLASS_TO_KWARGS_NAMES: dict[type[Timeline], list[str]] = {
    BeatTimeline: ["name", "height", "beat_pattern"],
    HierarchyTimeline: ["name", "height"],
    MarkerTimeline: ["name", "height"],
    RangeTimeline: ["name", "height", "default_row_height"],
    ScoreTimeline: ["name", "height"],
}

# Optional argument attribute -> the flag to name in error messages.
# "name" is absent because every kind accepts it.
OPTIONAL_ARG_TO_FLAG = {
    "beat_pattern": "--beat-pattern",
    "default_row_height": "--row-height",
    "height": "--height",
}


def setup_parser(subparser):
    add_subp = subparser.add_parser(
        "add",
        exit_on_error=False,
        help="Add a new timeline",
        epilog="""
Examples:
  timelines add beat --name "Measures" --beat-pattern 4
  timelines add hierarchy --name "Form"
  timelines add marker --name "Cadences"
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_subp.add_argument(
        "kind",
        choices=list(KIND_STR_TO_TIMELINE_CLASS),
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
        type=int,
        nargs="+",
        default=None,
        help="Pattern as space-separated integers indicating beat count in a measure "
        "(beat timelines only). Pattern will be repeated. Pattern '3 4', for "
        "instance, will alternate measures of 3 and 4 beats. Defaults to [4].",
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


def get_kwargs_by_timeline_type(namespace: argparse.Namespace, kind: type[Timeline]):
    kwargs = {}
    for attr in TIMELINE_CLASS_TO_KWARGS_NAMES[kind]:
        kwargs[attr] = getattr(namespace, attr)
    return kwargs


def add(namespace: argparse.Namespace):
    if not get(Get.MEDIA_DURATION):
        tilia.errors.display(tilia.errors.CLI_CREATE_TIMELINE_WITHOUT_DURATION)
        return
    kind = namespace.kind
    name = namespace.name

    tl_type = KIND_STR_TO_TIMELINE_CLASS[kind]
    accepted_kwargs = TIMELINE_CLASS_TO_KWARGS_NAMES[tl_type]

    for attr, flag in OPTIONAL_ARG_TO_FLAG.items():
        if getattr(namespace, attr) is not None and attr not in accepted_kwargs:
            tilia.errors.display(
                tilia.errors.CLI_ADD_TIMELINE_ARG_NOT_APPLICABLE, flag, kind
            )
            return

    output(f"Adding timeline with {kind=}, {name=}")

    kwargs = get_kwargs_by_timeline_type(namespace, tl_type)

    get(Get.TIMELINE_COLLECTION).create_timeline(tl_type, **kwargs)
