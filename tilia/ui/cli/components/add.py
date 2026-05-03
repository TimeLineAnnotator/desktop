import argparse
from functools import partial

from tilia.timelines.base.timeline import Timeline
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.ui.cli.io import output
from tilia.ui.cli.timelines.utils import get_timeline_by_name, get_timeline_by_ordinal

COMPONENT_KIND_TO_PARAMS = {
    ComponentKind.BEAT: ["time"],
    ComponentKind.HIERARCHY: ["start", "end", "level", "label"],
    ComponentKind.MARKER: ["time", "label"],
}


def setup_parser(subparser):
    subp = subparser.add_parser(
        "beat",
        exit_on_error=False,
        help="Add a beat component to a timeline",
        epilog="""
Examples:
  components beat --tl-name "Measures" --time 10.5
  components beat --tl-ordinal 1 --time 20.0
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    tl_group = subp.add_mutually_exclusive_group(required=True)
    tl_group.add_argument(
        "--tl-ordinal",
        "-o",
        type=int,
        default=None,
        help="Ordinal of the target timeline",
    )
    tl_group.add_argument(
        "--tl-name", "-n", type=str, default=None, help="Name of the target timeline"
    )
    subp.add_argument(
        "--time", "-t", type=float, required=True, help="Time position for the beat"
    )
    subp.set_defaults(func=partial(add, BeatTimeline))


def validate_timeline(
    namespace: argparse.Namespace, tl_type: type(Timeline), tl: Timeline
):
    if not tl:
        if namespace.tl_ordinal is not None:
            raise ValueError(f"No timeline found with ordinal={namespace.tl_ordinal}")
        else:
            raise ValueError(f"No timeline found with name={namespace.tl_name}")

    if not isinstance(tl, tl_type):
        raise ValueError(f"Timeline {tl} is of wrong kind. Expected {tl_type}")


def get_component_params(cmp_kind: ComponentKind, namespace: argparse.Namespace):
    params = {}
    for attr in COMPONENT_KIND_TO_PARAMS[cmp_kind]:
        params[attr] = getattr(namespace, attr)
    return params


def add(tl_type: type(Timeline), namespace: argparse.Namespace):
    ordinal = namespace.tl_ordinal
    name = namespace.tl_name

    if ordinal is not None:
        success, tl = get_timeline_by_ordinal(ordinal)
    else:
        success, tl = get_timeline_by_name(name)

    validate_timeline(namespace, tl_type, tl)

    TL_TYPE_TO_COMPONENT_KIND = {
        BeatTimeline: ComponentKind.BEAT,
        HierarchyTimeline: ComponentKind.HIERARCHY,
        MarkerTimeline: ComponentKind.MARKER,
    }

    cmp_kind = TL_TYPE_TO_COMPONENT_KIND[tl_type]
    params = get_component_params(cmp_kind, namespace)

    tl.create_component(cmp_kind, **params)

    output(f"Adding component to timeline {tl}")
