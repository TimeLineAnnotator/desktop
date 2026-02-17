import argparse
from functools import partial
from tilia.timelines.component_kinds import ComponentKind

from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.cli import io
from tilia.ui.cli.io import output
from tilia.ui.cli.timelines.utils import get_timeline_by_ordinal, get_timeline_by_name

TL_KIND_TO_COMPONENT_KIND = {
    TlKind.BEAT_TIMELINE: ComponentKind.BEAT,
    TlKind.HIERARCHY_TIMELINE: ComponentKind.HIERARCHY,
    TlKind.MARKER_TIMELINE: ComponentKind.MARKER,
}

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
    subp.set_defaults(func=partial(add, TlKind.BEAT_TIMELINE))


def get_component_params(cmp_kind: ComponentKind, namespace: argparse.Namespace):
    params = {}
    for attr in COMPONENT_KIND_TO_PARAMS[cmp_kind]:
        params[attr] = getattr(namespace, attr)
    return params


def add(tl_kind: TlKind, namespace: argparse.Namespace):
    ordinal = namespace.tl_ordinal
    name = namespace.tl_name

    if ordinal is not None:
        success, tl = get_timeline_by_ordinal(ordinal)
    else:
        success, tl = get_timeline_by_name(name)

    if not success:
        return

    if tl.KIND != tl_kind:
        io.error(f"Timeline {tl} is of wrong kind. Expected {tl_kind}")
        return

    cmp_kind = TL_KIND_TO_COMPONENT_KIND[tl_kind]
    params = get_component_params(cmp_kind, namespace)

    tl.create_component(cmp_kind, **params)

    output(f"Adding component to timeline {tl}")
