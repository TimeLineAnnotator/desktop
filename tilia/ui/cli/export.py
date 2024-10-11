from pathlib import Path

from tilia.requests import post, Post
from tilia.ui.cli import io


def setup_parser(subparsers):
    parser = subparsers.add_parser("export", exit_on_error=False)

    parser.add_argument("path", help="Path to save file to.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing file.")

    parser.set_defaults(func=export)


def export(namespace):
    path = Path(namespace.path)

    if path.exists() and not namespace.overwrite:
        if not io.ask_yes_or_no(f"File {path} already exists. Overwrite?"):
            return

    post(Post.FILE_EXPORT, str(path.resolve()))
