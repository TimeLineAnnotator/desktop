from argparse import _SubParsersAction

from tilia.exceptions import TiliaExit


def setup_parser(subparsers: _SubParsersAction):
    _quit = subparsers.add_parser("quit", aliases=["exit", "q"])
    _quit.set_defaults(func=quit)


def quit(_):
    print("Quitting...")
    raise TiliaExit
