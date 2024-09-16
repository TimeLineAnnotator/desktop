import time
from pathlib import Path

import tilia.errors
from tilia.requests import Post, post, get, Get
from tilia.ui.cli import io


def setup_parser(subparsers):
    parser = subparsers.add_parser("load-media", exit_on_error=False)

    parser.add_argument(
        "path",
        type=str,
        help="Path to media.",
    )

    parser.add_argument(
        "-s", "--scale-timelines",
        type=str,
        choices=["yes", "no", "prompt"],
        default='prompt',
        help="Automatically scale the media timeline.",
    )
    parser.set_defaults(func=load_media)


def load_media(namespace):
    path = Path(namespace.path)
    if not path.exists():
        tilia.errors.display(tilia.errors.MEDIA_NOT_FOUND, path)
        return

    post(Post.APP_MEDIA_LOAD, str(path.resolve()).replace("\\", "/"), scale_timelines=namespace.scale_timelines)

    time.sleep(0.1)  # conservative estimate for QMediaPlayer to load the file
    duration = get(Get.MEDIA_DURATION)
    if duration:
        io.output(f"Media loaded, duration is {duration}.")
    else:
        io.output("No media duration available, loading may have failed. You can set a duration manually with 'metadata set-media-length'")

