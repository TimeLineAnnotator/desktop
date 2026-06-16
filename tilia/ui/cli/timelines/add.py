import argparse

import tilia.errors
from tilia.requests import Get, get
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.ui.cli.io import output


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
        choices=["hierarchy", "hrc", "marker", "mrk", "beat", "bea", "score", "sco"],
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
        default=[4],
        help="Pattern as space-separated integers indicating beat count in a measure. Pattern will be repeated. Pattern '3 4', for instance, will alternate measures of 3 and 4 beats.",
    )
    add_subp.set_defaults(func=add)


TLKIND_TO_KWARGS_NAMES = {
    BeatTimeline: ["name", "height", "beat_pattern"],
    HierarchyTimeline: ["name", "height"],
    MarkerTimeline: ["name", "height"],
    ScoreTimeline: ["name", "height"],
}


def get_kwargs_by_timeline_type(namespace: argparse.Namespace, kind: type(Timeline)):
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
    }

    if not get(Get.MEDIA_DURATION):
        tilia.errors.display(tilia.errors.CLI_CREATE_TIMELINE_WITHOUT_DURATION)
        return
    kind = namespace.kind
    name = namespace.name

    output(f"Adding timeline with {kind=}, {name=}")

    tl_type = KIND_STR_TO_TLKIND[kind]

    kwargs = get_kwargs_by_timeline_type(namespace, tl_type)

    get(Get.TIMELINE_COLLECTION).create_timeline(tl_type, **kwargs)
