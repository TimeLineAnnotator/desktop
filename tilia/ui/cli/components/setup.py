from argparse import _SubParsersAction

from .add import setup_parser as setup_add_parser


def setup_parser(subparsers: _SubParsersAction):
    tl = subparsers.add_parser(
        "components", exit_on_error=False, aliases=["cmp", "component"]
    )
    tl_subparser = tl.add_subparsers(dest="component_command")

    setup_add_parser(tl_subparser)
