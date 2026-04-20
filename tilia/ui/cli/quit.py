from functools import partial


def setup_parser(subparsers, exit):
    _quit = subparsers.add_parser(
        "quit", aliases=["exit", "q"], help="Quit the application"
    )
    _quit.set_defaults(func=partial(exit, 0))
