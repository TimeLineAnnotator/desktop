
from tilia.boot import boot
import tkinter as tk
import argparse

from tilia.ui.cli.ui import CLI
from tilia.ui.tkinterui import TkinterUI


def create_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-interface", default="tkinter")
    parser.add_argument("--cmd", default="")
    parser.add_argument(
        "--logging",
        "-l",
        choices=["CRITICAL", "ERROR", "WARN", "INFO", "DEBUG", "TRACE"],
        default="INFO",
    )

    return parser


def main() -> None:
    boot()

    parser = create_argparser()
    args = parser.parse_args()

    if args.user_interface == "tkinter":
        root = tk.Tk()
        ui = TkinterUI(root)
    elif args.user_interface == "cli":
        ui = CLI()
    else:
        raise ValueError(
            f'Got invalid value "{args.user_interface}" for "user_interface"'
        )


if __name__ == "__main__":
    main()
