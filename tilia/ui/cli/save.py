from tilia.file.common import validate_save_path
from tilia.requests import post, Post
from tilia.ui.cli import io
from tilia.ui.cli.common import Subparsers

from pathlib import Path


def setup_parser(subparsers: Subparsers):
    parser = subparsers.add_parser('save', exit_on_error=False)

    parser.add_argument('path', help='Path to save file to.')

    parser.set_defaults(func=save)


def ensure_tla_extension(path: Path) -> Path:
    if not path.suffix == '.tla':
        path = path.with_name(f"{path.name}.tla")
    return path


def ask_overwrite_save_path(path: Path):
    return io.ask_yes_or_no(f'File {path} already exists. Overwrite?')


def save(namespace):
    path = Path(namespace.path)
    path = ensure_tla_extension(path)

    if path.exists():
        if not ask_overwrite_save_path(path):
            return

    validate_save_path(path)
    post(Post.REQUEST_SAVE_TO_PATH, path)
