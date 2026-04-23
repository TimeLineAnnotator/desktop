import argparse
from pathlib import Path

import tilia.errors
from tilia.file.common import validate_save_path
from tilia.requests import Post, post
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
