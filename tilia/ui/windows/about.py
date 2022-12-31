import tkinter as tk


class AboutWindow:
    def __init__(self):
        super(AboutWindow, self).__init__()
        self.title(f"{globals_.APP_NAME}")
        tk.Label(self, text=globals_.APP_NAME).pack()
        tk.Label(self, text=f"Version {globals_.VERSION}").pack()
        # TODO add licensing information
        tk.Label(self, text="Felipe Defensor").pack()
        tk.Label(self, text="https://github.com/FelipeDefensor/TiLiA").pack()