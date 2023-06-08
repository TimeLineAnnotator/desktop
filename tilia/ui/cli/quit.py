import sys

from tilia.exceptions import TiliaExit
from tilia.ui.cli.common import Subparsers


def setup_parser(subparsers: Subparsers):
    _quit = subparsers.add_parser("quit")
    _quit.set_defaults(func=quit)


def quit(_):
    print("Quitting...")
    raise TiliaExit
