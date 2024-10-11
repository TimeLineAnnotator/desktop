from pathlib import Path

from tilia.requests import post, Post
from tilia.ui.path import ensure_tla_extension


def setup_parser(subparsers):
    parser = subparsers.add_parser("open", exit_on_error=False)

    parser.add_argument("path", help="Path to TiLiA file.", type=str)

    parser.set_defaults(func=open)


def open(namespace):
    path = Path(namespace.path)
    path = ensure_tla_extension(path)

    post(Post.FILE_OPEN, str(path.resolve()))
