import argparse
from tilia.requests import post, Post


def setup_parser(subparsers):
    parser = subparsers.add_parser("import", help="Import metadata from JSON file.")
    parser.add_argument("path", type=str, help="Path to JSON file.")

    parser.set_defaults(func=import_metadata)


def import_metadata(namespace: argparse.Namespace):
    post(Post.REQUEST_IMPORT_MEDIA_METADATA_FROM_PATH, "".join(namespace.path))
