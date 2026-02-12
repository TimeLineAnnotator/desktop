import argparse
from colorama import Fore

from tilia.requests import get, Get
from tilia.ui.cli import io
from tilia.ui.cli.timelines.utils import get_timeline_by_name, get_timeline_by_ordinal


def setup_parser(subparser):
    remove_subp = subparser.add_parser(
        "remove",
        exit_on_error=False,
        aliases=["rm"],
        help="Remove a timeline",
        epilog="""
Examples:
  # Remove timeline named "Measures"
  timelines remove name "Measures"

  # Remove top-most timeline
  timelines remove ordinal 1
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    remove_subcommands = remove_subp.add_subparsers(dest="type", required=True)

    # 'remove by name' subcommand
    by_name_subcommand = remove_subcommands.add_parser(
        "name", exit_on_error=False, help="Remove timeline by name"
    )
    by_name_subcommand.add_argument("name", help="Name of the timeline to remove")
    by_name_subcommand.set_defaults(func=remove_timeline, by="name")

    # 'remove by ordinal' subcommand
    by_ordinal_subcommand = remove_subcommands.add_parser(
        "ordinal", exit_on_error=False, help="Remove timeline by ordinal"
    )
    by_ordinal_subcommand.add_argument(
        "ordinal", type=int, help="Ordinal of the timeline to remove"
    )
    by_ordinal_subcommand.set_defaults(func=remove_timeline, by="ordinal")


def remove_timeline(namespace):
    attr_value = getattr(namespace, namespace.by)

    if namespace.by == "name":
        success, tl = get_timeline_by_name(attr_value)
    else:  # ordinal
        success, tl = get_timeline_by_ordinal(attr_value)

    if not success:
        return
    else:
        io.output(f"Removing timeline {tl=}", Fore.GREEN)

    get(Get.TIMELINE_COLLECTION).delete_timeline(tl)
