import argparse
from tilia.file.media_metadata import MediaMetadata
from tilia.requests.get import Get, get
from tilia.ui.cli import io


def setup_parser(subparsers: argparse._SubParsersAction):
    parser = subparsers.add_parser("show", help="Import metadata from JSON file.")
    parser.set_defaults(func=show)


def show(_: argparse.Namespace):
    io.output(format_metadata(get(Get.MEDIA_METADATA)))


def format_metadata(metadata: MediaMetadata):
    return "\n".join([f"{k.capitalize()}: {v}" for k, v in metadata.items()])
