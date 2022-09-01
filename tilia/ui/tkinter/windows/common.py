from __future__ import annotations

import tkinter as tk

from tilia import globals_


class AppWindow(tk.Toplevel):
    def __init__(self, *args, **kwargs):
        super(AppWindow, self).__init__(*args, **kwargs)
        try:
            self.transient(globals_.APP.parent)
        except AttributeError:
            # app is not loaded yet
            pass
        self.iconbitmap(".\\img\\main_icon.ico")
        self.bind("<Escape>", lambda x: self.destroy())