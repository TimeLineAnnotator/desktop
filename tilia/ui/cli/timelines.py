from tilia.requests import post, Post, get, Get
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.cli.common import Subparsers
from tilia.ui.cli.output import tabulate


def setup_parser(subparsers: Subparsers):
    tl = subparsers.add_parser("timeline", exit_on_error=False)
    tl_subparser = tl.add_subparsers(dest="timeline_command")

    # 'add' subparser
    add_subp = tl_subparser.add_parser("add", exit_on_error=False)
    add_subp.add_argument(
        "kind", choices=["hierarchy", "hrc", "marker", "mrk", "beat", "bea"]
    )
    add_subp.add_argument("--name", default="")
    add_subp.set_defaults(func=add)

    # 'list' subparser
    list_subp = tl_subparser.add_parser("list", exit_on_error=False)
    list_subp.set_defaults(func=list)

    # 'remove' subparser
    remove_subp = tl_subparser.add_parser("remove", exit_on_error=False)
    remove_subcommands = remove_subp.add_subparsers(dest="type", required=True)

    # 'remove by name' subcommand
    remove_by_name_subc = remove_subcommands.add_parser("name", exit_on_error=False)
    remove_by_name_subc.add_argument("name")
    remove_by_name_subc.set_defaults(func=remove_by_name)

    # 'remove by ordinal' subcommand
    remove_by_ordinal_subc = remove_subcommands.add_parser(
        "ordinal", exit_on_error=False
    )
    remove_by_ordinal_subc.add_argument("ordinal", type=int)
    remove_by_ordinal_subc.set_defaults(func=remove_by_ordinal)


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
    headers = ["ord.", "name", "kind"]
    data = [
        (
            tl.ordinal,
            tl.name,
            pprint_tlkind(tl.KIND),
        )
        for tl in timelines
    ]
    tabulate(headers, data)


def remove_by_name(namespace):
    tl = get(Get.TIMELINE_BY_ATTR, "name", namespace.name)

    if not tl:
        raise ValueError(f"No timeline found with name={namespace.name}")

    print(f"Removing timeline {tl=}")

    post(Post.REQUEST_TIMELINE_DELETE, tl.id)


def remove_by_ordinal(namespace):
    tl = get(Get.TIMELINE_BY_ATTR, "ordinal", namespace.ordinal)

    if not tl:
        raise ValueError(f"No timeline found with ordinal={namespace.ordinal}")

    print(f"Removing timeline {tl=}")

    post(Post.REQUEST_TIMELINE_DELETE, tl.id)


def get_timeline_by_name(name: str) -> Timeline:
    result = [tl for tl in get(Get.TIMELINES) if tl.name == name]
    return result[0] if result else None


def get_timeline_by_id(id: str) -> Timeline | None:
    result = [tl for tl in get(Get.TIMELINES) if tl.id == id]
    return result[0] if result else None


def pprint_tlkind(kind: TlKind) -> str:
    return kind.value.strip("_TIMELINE").capitalize()
