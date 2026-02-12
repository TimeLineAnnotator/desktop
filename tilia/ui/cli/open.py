from pathlib import Path

from tilia.ui import commands
from tilia.ui.path import ensure_tla_extension


def setup_parser(subparsers):
    parser = subparsers.add_parser(
        "open", exit_on_error=False, help="Open a TiLiA file"
    )

    parser.add_argument("path", help="Path to TiLiA file", type=str)

    parser.set_defaults(func=open)


def open(namespace):
    path = Path(namespace.path)
    path = ensure_tla_extension(path)

    commands.execute("file.open", str(path.resolve()))
