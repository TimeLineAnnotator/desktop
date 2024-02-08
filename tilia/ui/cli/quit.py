from tilia.exceptions import TiliaExit
from tilia.ui.cli import io


def setup_parser(subparsers):
    _quit = subparsers.add_parser("quit", aliases=["exit", "q"])
    _quit.set_defaults(func=quit)


# noinspection PyShadowingBuiltins
def quit(_):
    io.output("Quitting...")
    raise TiliaExit
