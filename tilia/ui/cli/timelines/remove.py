from tilia.requests import get, Get, Post, post
from tilia.ui.cli.server import ServeTimelineUIFromCLI


def setup_parser(subparser):
    remove_subp = subparser.add_parser("remove", exit_on_error=False, aliases=["rm"])
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


def remove_by_name(namespace):
    tl = get(Get.TIMELINE_BY_ATTR, "name", namespace.name)

    if not tl:
        raise ValueError(f"No timeline found with name={namespace.name}")

    print(f"Removing timeline {tl=}")

    with ServeTimelineUIFromCLI(get(Get.TIMELINE_UI, tl.id)):
        post(Post.TIMELINE_DELETE_FROM_CLI)


def remove_by_ordinal(namespace):
    tl = get(Get.TIMELINE_BY_ATTR, "ordinal", namespace.ordinal)

    if not tl:
        raise ValueError(f"No timeline found with ordinal={namespace.ordinal}")

    print(f"Removing timeline {tl=}")

    with ServeTimelineUIFromCLI(get(Get.TIMELINE_UI, tl.id)):
        post(Post.TIMELINE_DELETE_FROM_CLI)
