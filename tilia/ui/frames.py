from __future__ import annotations

import tkinter as tk

from tilia import settings
from tilia.requests import Post, post
from tilia.ui import player
from tilia.ui.timelines.common import TimelineCanvas
from tilia.ui.widgets import CheckboxItem


class AppToolbarsFrame(tk.Frame):
    def __init__(self, *args, **kwargs):
        super(AppToolbarsFrame, self).__init__(*args, **kwargs)

        self.playback_frame = player.PlayerUI(self)

        self.auto_scroll_checkbox = CheckboxItem(
            label="Auto-scroll",
            value=settings.get("general", "auto-scroll"),
            set_func=lambda: settings.edit(
                "general", "auto-scroll", self.auto_scroll_checkbox.variable.get()
            ),
            parent=self,
        )

        self.playback_frame.pack(side=tk.LEFT, anchor=tk.W)
        self.auto_scroll_checkbox.pack(side=tk.LEFT, anchor=tk.W)


class ScrollableFrame(tk.Frame):
    """Tk.Frame does not support scrolling. This workaround relies
    on a frame placed inside a canvas, a widget which does support scrolling.
    self.frame is the frame that must be used by outside widgets."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0, bg=TimelineCanvas.DEFAULT_BG)
        self.frame = tk.Frame(self.canvas)
        self.vsb = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.create_window((0, 0), window=self.frame, anchor="nw")

        self.frame.bind("<Configure>", self.on_frame_configure)
        self.canvas.bind(
            "<Configure>",
            lambda e: post(Post.ROOT_WINDOW_RESIZED, e.width, e.height),
        )

    def on_frame_configure(self, _):
        """Reset the scroll region to encompass the inner frame"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
