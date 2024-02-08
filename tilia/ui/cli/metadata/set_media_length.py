import argparse
from tilia.requests import post, Post
from tilia.ui.cli import io


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
        post(
            Post.DISPLAY_ERROR,
            "Set media metadata",
            "Can't set media metadata to {value}. Media length must be a number.",
        )
        return False

    if value < 0:
        post(
            Post.DISPLAY_ERROR,
            "Set media metadata",
            "Can't set media metadata to {value}. Media length must be a number.",
        )
        io.output("Can't set to {value}. Media length must be positive.")
        return False

    return True


def set_media_length(namespace: argparse.Namespace):
    if validate_value(namespace.value):
        post(Post.PLAYER_DURATION_CHANGED, namespace.value)
