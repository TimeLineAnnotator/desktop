

from tilia.requests import Post, post


def setup_parser(subparsers):
    parser = subparsers.add_parser("load-media", exit_on_error=False)

    parser.add_argument(
        "path",
        type=str,
        help="Path to media.",
        nargs="+",  # needed to parse paths with spaces
    )

    parser.set_defaults(func=load_media)


def load_media(namespace):
    path = " ".join(namespace.path).strip('"')  # for paths with spaces or double quotes

    post(Post.APP_MEDIA_LOAD, path)
