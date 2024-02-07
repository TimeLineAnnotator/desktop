from argparse import _SubParsersAction

from .imp import setup_parser as setup_import_parser
from .add import setup_parser as setup_add_parser
from .list import setup_parser as setup_list_parser
from .remove import setup_parser as setup_remove_parser


def setup_parser(subparsers: _SubParsersAction):
    tl = subparsers.add_parser(
        "timelines", exit_on_error=False, aliases=["tl", "timeline"]
    )
    tl_subparser = tl.add_subparsers(dest="timeline_command")

    setup_add_parser(tl_subparser)
    setup_list_parser(tl_subparser)
    setup_remove_parser(tl_subparser)
    setup_import_parser(tl_subparser)
