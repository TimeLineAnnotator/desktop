import argparse

import tilia
import tilia.errors
from tilia.exceptions import MediaMetadataFieldNotFound
from tilia.requests import post, Post


def setup_parser(subparsers):

    parser = subparsers.add_parser("set", help="Set media metadata.")
    parser.add_argument("field", type=str, help="Field name.")
    parser.add_argument("value", type=str, help="Field value.")

    parser.set_defaults(func=set_metadata)


def set_metadata(namespace: argparse.Namespace):
    if namespace.field.lower() == 'media length':
        tilia.errors.display(
            tilia.errors.CLI_METADATA_CANT_SET_MEDIA_LENGTH
        )
        return
    try:
        post(Post.MEDIA_METADATA_FIELD_SET, namespace.field, namespace.value)
    except MediaMetadataFieldNotFound:
        tilia.errors.display(tilia.errors.METADATA_FIELD_NOT_FOUND, namespace.field)
