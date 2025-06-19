from tilia.requests import post, Post, Get, get
from tilia.ui.cli import io


def setup_parser(subparsers):
    parser = subparsers.add_parser("clear", exit_on_error=False)

    parser.add_argument(
        "--force", action="store_true", help="Do not ask for confirmation."
    )

    parser.set_defaults(func=save)


def save(namespace):
    if not namespace.force:
        if get(Get.IS_FILE_MODIFIED):
            if not io.ask_yes_or_no("There are unsaved changes. Clear anyway?"):
                return

    post(Post.APP_CLEAR)
    post(Post.APP_SETUP_FILE)
