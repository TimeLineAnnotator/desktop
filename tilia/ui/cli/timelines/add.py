import argparse

import tilia.errors
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.requests import get, Get
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


KIND_STR_TO_TLKIND = {
    "hierarchy": TlKind.HIERARCHY_TIMELINE,
    "hrc": TlKind.HIERARCHY_TIMELINE,
    "marker": TlKind.MARKER_TIMELINE,
    "mrk": TlKind.MARKER_TIMELINE,
    "beat": TlKind.BEAT_TIMELINE,
    "bea": TlKind.BEAT_TIMELINE,
    "score": TlKind.SCORE_TIMELINE,
    "sco": TlKind.SCORE_TIMELINE,
}

TLKIND_TO_KWARGS_NAMES = {
    TlKind.BEAT_TIMELINE: ["name", "height", "beat_pattern"],
    TlKind.HIERARCHY_TIMELINE: ["name", "height"],
    TlKind.MARKER_TIMELINE: ["name", "height"],
    TlKind.SCORE_TIMELINE: ["name", "height"],
}


def get_kwargs_by_timeline_kind(namespace: argparse.Namespace, kind: TlKind):
    kwargs = {}
    for attr in TLKIND_TO_KWARGS_NAMES[kind]:
        kwargs[attr] = getattr(namespace, attr)
    return kwargs


def add(namespace: argparse.Namespace):
    if not get(Get.MEDIA_DURATION):
        tilia.errors.display(tilia.errors.CLI_CREATE_TIMELINE_WITHOUT_DURATION)
        return
    kind = namespace.kind
    name = namespace.name

    output(f"Adding timeline with {kind=}, {name=}")

    tl_kind = KIND_STR_TO_TLKIND[kind]
    kwargs = get_kwargs_by_timeline_kind(namespace, tl_kind)

    get(Get.TIMELINE_COLLECTION).create_timeline(tl_kind, **kwargs)
