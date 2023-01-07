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

from pathlib import Path
import os
import logging
import tkinter as tk

from typing import TYPE_CHECKING

from tilia._tilia import TiLiA

if TYPE_CHECKING:
    pass

from tilia import globals_
from tilia.ui.tkinterui import TkinterUI

logger = logging.getLogger(__name__)


def main():
    logging.basicConfig(
        filename=Path(globals_.DATA_DIR, 'log.txt'),
        filemode='w',
        level=logging.DEBUG,
        format=" %(name)-50s %(lineno)-5s %(levelname)-8s %(message)s"
    )

    os.chdir(os.path.dirname(__file__))

    root = tk.Tk()
    ui = TkinterUI(root)
    TiLiA(ui)
    ui.launch()


if __name__ == "__main__":
    main()
