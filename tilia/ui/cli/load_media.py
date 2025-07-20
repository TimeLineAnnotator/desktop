import argparse
import re
from functools import partial
from pathlib import Path
from typing import Callable

import tilia.constants
import tilia.errors
from tilia.requests import Post, post, get, Get
from tilia.ui.cli import io


def setup_parser(subparsers, parse_and_run: Callable[[str], bool]):
    parser = subparsers.add_parser("load-media", exit_on_error=False)

    parser.add_argument(
        "path",
        type=str,
        help="Path to media.",
    )

    parser.add_argument(
        "-s",
        "--scale-timelines",
        type=str,
        choices=["yes", "no", "prompt"],
        default="prompt",
        help="Automatically scale the media timeline.",
    )

    parser.add_argument(
        "--duration-if-error",
        type=float,
        default=None,
        help="Duration to use if media could not be loaded.",
    )

    parser.set_defaults(func=partial(load_media, parse_and_run))


def load_media(parse_and_run: Callable[[str], bool], namespace: argparse.Namespace):
    if re.match(tilia.constants.YOUTUBE_URL_REGEX, namespace.path):
        path = namespace.path
    else:
        path = Path(namespace.path.replace("\\", "/"))
        if not path.exists():
            tilia.errors.display(tilia.errors.MEDIA_NOT_FOUND, path)
            return
        path = str(path.resolve()).replace("\\", "/")

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
