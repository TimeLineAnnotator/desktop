import argparse

import tilia.errors
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.requests import post, Post, get, Get
from tilia.ui.cli.io import output


def setup_parser(subparser):
    add_subp = subparser.add_parser("add", exit_on_error=False)
    add_subp.add_argument(
        "kind", choices=["hierarchy", "hrc", "marker", "mrk", "beat", "bea"]
    )
    add_subp.add_argument("--name", "-n", type=str, default="")
    add_subp.add_argument("--height", "-e", type=int, default=None)
    add_subp.add_argument("--beat-pattern", "-b", type=int, nargs="+", default=[4])
    add_subp.set_defaults(func=add)


KIND_STR_TO_TLKIND = {
    "hierarchy": TlKind.HIERARCHY_TIMELINE,
    "hrc": TlKind.HIERARCHY_TIMELINE,
    "marker": TlKind.MARKER_TIMELINE,
    "mrk": TlKind.MARKER_TIMELINE,
    "beat": TlKind.BEAT_TIMELINE,
    "bea": TlKind.BEAT_TIMELINE,
}

TLKIND_TO_KWARGS_NAMES = {
    TlKind.BEAT_TIMELINE: ["name", "height", "beat_pattern"],
    TlKind.HIERARCHY_TIMELINE: ["name", "height"],
    TlKind.MARKER_TIMELINE: ["name", "height"],
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

    post(Post.TIMELINE_ADD, tl_kind, **kwargs)
