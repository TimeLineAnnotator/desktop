import argparse
from typing import Protocol

from tilia.requests import post, Post, get, Get
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.cli.output import tabulate


class Subparser(Protocol):
    def add_parser(self, *args, **kwargs) -> argparse.ArgumentParser: ...


def setup_parser(subparsers: Subparser):
    tl = subparsers.add_parser("timeline")
    tl_subparser = tl.add_subparsers(dest="timeline_command")

    # 'add' subparser
    add_subp = tl_subparser.add_parser("add")
    add_subp.add_argument(
        "kind", choices=["hierarchy", "hrc", "marker", "mrk", "beat", "bea"]
    )
    add_subp.add_argument("--name", default="")
    add_subp.set_defaults(func=add)

    # 'list' subparser
    list_subp = tl_subparser.add_parser("list")
    list_subp.set_defaults(func=list)

    # 'remove' subparser
    remove_subp = tl_subparser.add_parser("remove")
    remove_subp.add_mutually_exclusive_group(required=True)
    remove_subp.add_argument("--name", "-n")
    remove_subp.add_argument("--id")
    # remove.set_defaults(func=remove_timeline)


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


def list(_):
    timelines = get(Get.TIMELINES)
    headers = ["id", "name", "kind"]
    data = [
        (
            tl.id,
            tl.name,
            pprint_tlkind(tl.KIND),
        )
        for tl in timelines
    ]
    tabulate(headers, data)


def get_timeline_by_name(name: str) -> Timeline:
    result = [tl for tl in get(Get.TIMELINES) if tl.name == name]
    return result[0] if result else None


def get_timeline_by_id(id: str) -> Timeline | None:
    result = [tl for tl in get(Get.TIMELINES) if tl.id == id]
    return result[0] if result else None


def pprint_tlkind(kind: TlKind) -> str:
    return kind.value.strip("_TIMELINE").capitalize()
