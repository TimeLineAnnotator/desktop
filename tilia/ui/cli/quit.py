def setup_parser(subparsers, exit):
    _quit = subparsers.add_parser(
        "quit", aliases=["exit", "q"], help="Quit the application"
    )
    _quit.set_defaults(func=exit)
