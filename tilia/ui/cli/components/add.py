import argparse
from functools import partial
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.component_kinds import ComponentKind

from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.cli.io import output
from tilia.ui.cli.timelines.getters import get_timeline_by_name, get_timeline_by_ordinal

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
    subp = subparser.add_parser("beat", exit_on_error=False)
    tl_group = subp.add_mutually_exclusive_group(required=True)
    tl_group.add_argument("--tl-ordinal", "-o", type=int, default=None)
    tl_group.add_argument("--tl-name", "-n", type=str, default=None)
    subp.add_argument("--time", "-t", type=float, required=True)
    subp.set_defaults(func=partial(add, TlKind.BEAT_TIMELINE))


def validate_timeline(namespace: argparse.Namespace, tl_kind: TlKind, tl: Timeline):
    if not tl:
        if namespace.tl_ordinal is not None:
            raise ValueError(f"No timeline found with ordinal={namespace.tl_ordinal}")
        else:
            raise ValueError(f"No timeline found with name={namespace.tl_name}")

    if tl.KIND != tl_kind:
        raise ValueError(f"Timeline {tl} is of wrong kind. Expected {tl_kind}")


def get_component_params(cmp_kind: ComponentKind, namespace: argparse.Namespace):
    params = {}
    for attr in COMPONENT_KIND_TO_PARAMS[cmp_kind]:
        params[attr] = getattr(namespace, attr)
    return params


def add(tl_kind: TlKind, namespace: argparse.Namespace):
    ordinal = namespace.tl_ordinal
    name = namespace.tl_name

    if ordinal is not None:
        tl = get_timeline_by_ordinal(ordinal)
    else:
        tl = get_timeline_by_name(name)

    validate_timeline(namespace, tl_kind, tl)

    cmp_kind = TL_KIND_TO_COMPONENT_KIND[tl_kind]
    params = get_component_params(cmp_kind, namespace)

    tl.create_component(cmp_kind, **params)

    output(f"Adding component to timeline {tl}")
