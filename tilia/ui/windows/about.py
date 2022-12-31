import tkinter as tk

from tilia import globals_, events
from tilia.events import Event


class About:
    def __init__(self, parent: tk.Tk):
        self.toplevel = tk.Toplevel(parent)
        self.toplevel.transient(parent)
        self.toplevel.title(f"About {globals_.APP_NAME}")
        self.toplevel.protocol("WM_DELETE_WINDOW", self.destroy)
        self.toplevel.focus()

        tk.Label(self.toplevel, text=globals_.APP_NAME).pack()
        tk.Label(self.toplevel, text=f"Version 0.2.0").pack()
        tk.Label(self.toplevel, text="www.timelineannotator.com").pack()
        tk.Label(self.toplevel, text="github.com/FelipeDefensor/TiLiA").pack()
        tk.Label(self.toplevel, text="License: CC BY-SA 4.0").pack()


    def destroy(self):
        self.toplevel.destroy()
        events.post(Event.ABOUT_WINDOW_CLOSED)
