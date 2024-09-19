import tilia.errors
from tilia.file.common import validate_save_path
from tilia.requests import post, Post
from tilia.ui.cli import io

from pathlib import Path


def setup_parser(subparsers):
    parser = subparsers.add_parser("save", exit_on_error=False)

    parser.add_argument("path", help="Path to save file to.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing file.")

    parser.set_defaults(func=save)


def ensure_tla_extension(path: Path) -> Path:
    if not path.suffix == ".tla":
        path = path.with_name(f"{path.name}.tla")
    return path


def ask_overwrite_save_path(path: Path):
    return io.ask_yes_or_no(f"File {path} already exists. Overwrite?")


def save(namespace):
    path = Path(namespace.path)
    path = ensure_tla_extension(path)

    if path.exists() and not namespace.overwrite:
        if not ask_overwrite_save_path(path):
            return

    valid, message = validate_save_path(path)
    if not valid:
        tilia.errors.display(tilia.errors.FILE_SAVE_FAILED, message)
        return

    post(Post.REQUEST_SAVE_TO_PATH, str(path.resolve()))
