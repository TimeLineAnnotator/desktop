import argparse
from pathlib import Path

import tilia.errors
from tilia.file.common import validate_save_path
from tilia.file.file_manager import same_path
from tilia.requests import Get, Post, get, post
from tilia.ui.cli import io
from tilia.ui.path import ensure_tla_extension


def setup_parser(subparsers):
    parser = subparsers.add_parser(
        "save",
        exit_on_error=False,
        help="Save the current project",
        epilog="""
Examples:
  # Save (prompts for overwrite if file exists)
  save /path/to/file.tla

  # Save (overwrites without prompting)
  save /path/to/file.tla --overwrite
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("path", help="Path to save the file")
    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing file"
    )

    parser.set_defaults(func=save)


def ask_overwrite_save_path(path: Path):
    return io.ask_yes_or_no(f"File {path} already exists. Overwrite?")


def save(namespace):
    path = ensure_tla_extension(Path(namespace.path))
    if _is_the_file_open(path):
        # As Save does in TiLiA's window: straight to the check before saving, with
        # or without --overwrite (TimeLineAnnotator/project-management#632, b).
        post(Post.REQUEST_SAVE_TO_PATH, str(path.resolve()))
        return
    path = confirmed_save_path(path, namespace.overwrite)
    if path is not None:
        post(Post.REQUEST_SAVE_TO_PATH, str(path))


def _is_the_file_open(path: Path) -> bool:
    open_path = get(Get.FILE_PATH)
    return bool(open_path) and same_path(path, open_path)


def confirmed_save_path(path: Path, overwrite: bool = False) -> Path | None:
    """`path`, with `.tla` added when missing, once overwriting a file there is
    confirmed, by `overwrite` or by the person, and it can be saved to. None
    otherwise, having said why a path can't be saved to."""
    path = ensure_tla_extension(path)

    if path.exists() and not overwrite:
        if not ask_overwrite_save_path(path):
            return None

    valid, message = validate_save_path(path)
    if not valid:
        tilia.errors.display(tilia.errors.FILE_SAVE_FAILED, message)
        return None

    return path.resolve()
