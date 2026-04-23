import argparse
from pathlib import Path

from tilia.ui import commands
from tilia.ui.cli import io


def setup_parser(subparsers):
    parser = subparsers.add_parser(
        "export",
        exit_on_error=False,
        help="Export to JSON",
        epilog="""
JSON format is described in https://tilia-app.com/help/export#json-format

Examples:
  # Export to JSON
  export /path/to/file.json

  # Export to JSON with overwrite
  export /path/to/file.json --overwrite
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("path", help="Path to export the file")
    parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing file"
    )

    parser.set_defaults(func=export)


def export(namespace):
    path = Path(namespace.path)

    if path.exists() and not namespace.overwrite:
        if not io.ask_yes_or_no(f"File {path} already exists. Overwrite?"):
            return

    commands.execute("file.export.json", str(path.resolve()))
