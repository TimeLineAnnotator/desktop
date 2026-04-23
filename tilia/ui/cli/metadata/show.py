import argparse

from tilia.file.media_metadata import MediaMetadata
from tilia.requests.get import Get, get
from tilia.ui.cli.io import tabulate


def setup_parser(subparsers):
    parser = subparsers.add_parser("show", help="Show current media metadata.")
    parser.set_defaults(func=show)


def show(_: argparse.Namespace):
    tabulate(
        ["key", "value"],
        format_metadata(get(Get.MEDIA_METADATA)),
        header=False,
        align="l",
        hrules=1,
    )


def format_metadata(metadata: MediaMetadata) -> list[tuple[str, str]]:
    return [(k.capitalize(), v) for k, v in metadata.items()]
