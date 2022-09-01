"""
Window that allows the user to center the app's view at a given measure.
Not reimplement yet.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk as ttk

from tilia import globals_
from tilia.ui.tkinter.windows.common import AppWindow

import logging

logger = logging.getLogger(__name__)


class GoToMeasureWindow(AppWindow):
    def __init__(self, *args, **kwargs):
        super(GoToMeasureWindow, self).__init__(*args, **kwargs)
        self.title("Go to measure")
        self.upper_frame = tk.Frame(self)
        self.combo_box = ttk.Combobox(self.upper_frame)
        self.combo_box["values"] = [
            f"{t.label_text}, {t.collection_id}"
            for t in globals_.APP._timeline_collection.objects
            if t.__class__.__name__ == "BeatTimeline"
        ]
        if not self.combo_box[
            "values"
        ]:  # there are no timelines that can hold measures
            globals_.APP.display_error("There are no beats marked.")
            self.destroy()
            return
        else:
            self.combo_box.current(0)
        self.combo_box["state"] = "readonly"
        self.combo_box.pack()

        from tilia.ui.tkinter.common import LabelAndEntry

        self.labelentry = LabelAndEntry(self.upper_frame, "Measure")
        self.labelentry.entry.configure(width=4)

        self.lower_frame = ConfirmCancelButtons(
            self,
            confirm_text="Go",
            confirm_command=self.on_go_press,
            cancel_command=lambda: self.destroy(),
        )

        self.labelentry.label.pack()
        self.labelentry.entry.pack()
        self.upper_frame.pack(padx=5, pady=5)
        self.lower_frame.pack(padx=5, pady=5)

        self.transient(globals_.APP.parent)
        self.focus()
        self.labelentry.entry.focus_set()

    def on_go_press(self):
        try:
            self.go_to_measure(
                self.get_timeline_from_combo_box(), int(self.labelentry.entry.get())
            )
        except ValueError:
            raise ValueError("Can't go to measure: measure number must be an integer.")

    def get_timeline_from_combo_box(self):
        id = self.combo_box.get().split()[1].strip()
        return globals_.APP._timeline_collection.find_by_collection_id(id)

    @staticmethod
    def go_to_measure(timeline, measure_number: int):
        """Center view and slide to given measure at given timeline"""
        try:
            measure = timeline.find_by_attribute(
                value=measure_number, attr="number", kind="measure"
            )[0]
            abs_pos = measure.abs_pos
        except IndexError:
            globals_.APP.display_error(
                f"Timeline has no measure numbered {measure_number}"
            )
            logger.info(
                f"User tried to go to non-existent measure number {measure_number} at timeline {timeline.collection_id}"
            )
            return

        globals_.APP.center_view_at(abs_pos * 2)
        timeline.seek_to_object(measure)
        return


class ConfirmCancelButtons(tk.Frame):
    def __init__(
        self,
        parent,
        confirm_text="Ok",
        confirm_command=None,
        cancel_text="Cancel",
        cancel_command=None,
    ):
        super().__init__(parent)
        self.confirm_button = tk.Button(
            self, text=confirm_text, command=confirm_command
        )
        self.confirm_button.pack(side=tk.LEFT, padx=10)
        self.cancel_button = tk.Button(self, text=cancel_text, command=cancel_command)
        self.cancel_button.pack(side=tk.RIGHT, padx=10)
        parent.bind("<Return>", lambda x: confirm_command())
