import argparse
from tilia.requests import post, Post
import tilia.errors


def setup_parser(subparsers):
    parser = subparsers.add_parser(
        "set-media-length", help="Import metadata from JSON file."
    )
    parser.add_argument("value", type=float, help="Media length value.")

    parser.set_defaults(func=set_media_length)


def validate_value(value: float) -> bool:
    """Returns True if value is value is a valid media length."""
    try:
        float(value)
    except ValueError:
        tilia.errors.display(tilia.errors.MEDIA_METADATA_SET_DATA_FAILED, value)
        return False

    if value <= 0:
        tilia.errors.display(tilia.errors.MEDIA_METADATA_SET_DATA_FAILED, value)
        return False

    return True


def set_media_length(namespace: argparse.Namespace):
    if validate_value(namespace.value):
        post(Post.PLAYER_DURATION_AVAILABLE, namespace.value)
