import argparse

import tilia
import tilia.errors
from tilia.exceptions import MediaMetadataFieldNotFound
from tilia.requests import Post, post


def setup_parser(subparsers):

    parser = subparsers.add_parser(
        "set",
        help="Set a specific metadata field.",
        epilog="""
Examples:
  metadata set title "Bohemian Rhapsody"
  metadata set composer "Chico Buarque"
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("field", type=str, help="Field name to set.")
    parser.add_argument("value", type=str, help="Value to set for the field.")

    parser.set_defaults(func=set_metadata)


def set_metadata(namespace: argparse.Namespace):
    if namespace.field.lower() == "media length":
        tilia.errors.display(tilia.errors.CLI_METADATA_CANT_SET_MEDIA_LENGTH)
        return
    try:
        post(Post.MEDIA_METADATA_FIELD_SET, namespace.field, namespace.value)
    except MediaMetadataFieldNotFound:
        post(Post.MEDIA_METADATA_FIELD_ADD, namespace.field)
        post(Post.MEDIA_METADATA_FIELD_SET, namespace.field, namespace.value)
