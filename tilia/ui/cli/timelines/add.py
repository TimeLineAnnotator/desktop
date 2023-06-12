from argparse import _SubParsersAction

from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.requests import post, Post


def setup_parser(subparser: _SubParsersAction):
    add_subp = subparser.add_parser("add", exit_on_error=False)
    add_subp.add_argument(
        "kind", choices=["hierarchy", "hrc", "marker", "mrk", "beat", "bea"]
    )
    add_subp.add_argument("--name", default="")
    add_subp.set_defaults(func=add)


def add(namespace):
    kind = namespace.kind
    name = namespace.name

    kind_to_tlkind = {
        "hierarchy": TlKind.HIERARCHY_TIMELINE,
        "hrc": TlKind.HIERARCHY_TIMELINE,
        "marker": TlKind.MARKER_TIMELINE,
        "mrk": TlKind.MARKER_TIMELINE,
        "beat": TlKind.BEAT_TIMELINE,
        "bea": TlKind.BEAT_TIMELINE,
    }

    print(f"Adding timeline with {kind=}, {name=}")

    post(Post.REQUEST_TIMELINE_CREATE, kind_to_tlkind[kind], name=name)
