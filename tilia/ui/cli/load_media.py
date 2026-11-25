import argparse
from functools import partial
from typing import Callable

import tilia.errors
from tilia.requests import Get, Post, get, post
from tilia.ui.cli import io
from tilia_core import build


def setup_parser(subparsers, parse_and_run: Callable[[str], bool]):
    parser = subparsers.add_parser(
        "load-media",
        exit_on_error=False,
        help="Load a media file",
        epilog="""
Examples:
  load-media "C:/path/to/media.mp3"
  load-media "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "path",
        type=str,
        help="Path to media",
    )

    parser.add_argument(
        "-s",
        "--scale-timelines",
        type=str,
        choices=["yes", "no", "prompt"],
        default="prompt",
        help="Automatically scale the media timeline",
    )

    parser.add_argument(
        "--duration-if-error",
        type=float,
        default=None,
        help="Duration to use if media could not be loaded",
    )

    parser.set_defaults(func=partial(load_media, parse_and_run))


def load_media(parse_and_run: Callable[[str], bool], namespace: argparse.Namespace):
    # The core decides, for a script's load-media too, what is media and the path
    # to store for it, so that a file stores the same whichever made it (FR-033).
    try:
        path = build.media_path(namespace.path)
    except ValueError as error:
        # MEDIA_NOT_FOUND's words, as the core says them: it quotes a link as a path
        # too, and writes a name that isn't UTF-8 so that it can be printed.
        post(Post.DISPLAY_ERROR, tilia.errors.MEDIA_NOT_FOUND.title, str(error))
        return

    success = post(
        Post.APP_MEDIA_LOAD,
        path,
        scale_timelines=namespace.scale_timelines,
    )

    if success:
        duration = get(Get.MEDIA_DURATION)
        io.output(f"Media loaded, duration is {duration}.")
    elif namespace.duration_if_error is not None:
        post(
            Post.DISPLAY_ERROR,
            "Load media warning",
            f"Loading media failed. Setting duration manually to {namespace.duration_if_error}.",
        )
        parse_and_run(f"metadata set-media-length {namespace.duration_if_error}")
    else:
        post(
            Post.DISPLAY_ERROR,
            "Load media warning",
            "Loading media has failed.",
        )
