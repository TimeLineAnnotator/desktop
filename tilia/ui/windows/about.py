import tkinter as tk

from tilia import globals_
from tilia.requests import Post, post


class About:
    def __init__(self, parent: tk.Tk):
        self.toplevel = tk.Toplevel(parent)
        self.toplevel.transient(parent)
        self.toplevel.title(f"About {globals_.APP_NAME}")
        self.toplevel.protocol("WM_DELETE_WINDOW", self.destroy)
        self.toplevel.focus()

        tk.Label(self.toplevel, text=globals_.APP_NAME).pack()
        tk.Label(self.toplevel, text=globals_.VERSION).pack()
        tk.Label(self.toplevel, text="www.timelineannotator.com").pack()
        tk.Label(self.toplevel, text="github.com/FelipeDefensor/App").pack()
        tk.Label(self.toplevel, text="License: CC BY-SA 4.0").pack()

    def focus(self):
        self.toplevel.focus_set()

    def destroy(self):
        self.toplevel.destroy()
        post(Post.ABOUT_WINDOW_CLOSED)
