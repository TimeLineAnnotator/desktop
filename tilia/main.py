"""
Entry point for the application.

Defines a TiLiA object which is composed, among other things, of instances of the following classes:
    - FileManager, which handles _file processing (open, save, new, etc...);
    - TimelineWithUIBuilder, which handles request to create timelines and their uis;
    - Player, which handles the playing of;
    - UI (currently a TkinterUI), which handles the GUI as a whole;
    - TimelineColleciton, which handles timeline logic/
    - TimelineUICollection, which handles the user interface for the timelines.

"""

from __future__ import annotations

import logging
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from tilia import dirs, settings
from tilia._tilia import TiLiA
from tilia.ui.tkinterui import TkinterUI

logger = logging.getLogger(__name__)


def main():
    dirs.setup_dirs()
    settings.load(dirs.settings_path)

    logging.basicConfig(
        filename=dirs.log_path,
        filemode="w",
        level=logging.DEBUG,
        format=" %(name)-50s %(lineno)-5s %(levelname)-8s %(message)s",
    )

    root = tk.Tk()
    ui = TkinterUI(root)
    TiLiA(ui)
    ui.launch()


if __name__ == "__main__":
    main()
