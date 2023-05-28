import logging
import tkinter as tk
import argparse

from tilia import dirs, settings
from tilia._tilia import TiLiA
from tilia.ui.tkinterui import TkinterUI

logger = logging.getLogger(__name__)


def main() -> None:
    dirs.setup_dirs()
    settings.load(dirs.settings_path)

    argparser = argparse.ArgumentParser()
    argparser.add_argument(
        "--logging",
        "-l",
        choices=["CRITICAL", "ERROR", "WARN", "INFO", "DEBUG", "TRACE"],
        default="INFO",
    )
    args = argparser.parse_args()

    logging.basicConfig(
        filename=dirs.log_path,
        filemode="w",
        level=args.logging,
        format=" %(name)-50s %(lineno)-5s %(levelname)-8s %(message)s",
    )

    root = tk.Tk()
    ui = TkinterUI(root)
    TiLiA(ui)
    ui.launch()


if __name__ == "__main__":
    main()
