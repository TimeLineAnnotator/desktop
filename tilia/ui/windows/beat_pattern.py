import tkinter as tk
from tkinter import scrolledtext
from typing import Literal

from tilia.ui.timelines.common import create_tool_tip


class AskBeatPattern:
    """Dialog for inserting beats per measure of a BeatTimeline()"""

    PROMPT = "Insert beat pattern (can be changed later):"
    TOOLTIP_TEXT = """Spaces separate measures, line breaks are ignored.
Examples:
  - '5' = 5 beats per measure;
  - '4 3 3' = a cycle of 4, then 3, then 3 beats per measure."""

    def __init__(self, parent: tk.Tk, initial_value=""):
        self.toplevel = tk.Toplevel(parent)
        self.toplevel.title("Insert beats per measure")
        self.toplevel.transient(parent)
        self.toplevel.focus_set()

        self.input_string = initial_value

        self.upper_frame = tk.Frame(self.toplevel)
        self.label = tk.Label(
            self.upper_frame,
            text=self.PROMPT,
        )
        self.help_label = tk.Label(self.upper_frame, text="ⓘ")
        create_tool_tip(self.help_label, text=self.TOOLTIP_TEXT)
        self.text = tk.scrolledtext.ScrolledText(self.toplevel, width=30, height=5)
        self.text.focus()
        self.confirm_cancel_frame = tk.Frame(self.toplevel)
        self.confirm_button = tk.Button(
            self.toplevel, text="Confirm", command=self.confirm
        )
        self.is_cancel = False
        self.cancel_button = tk.Button(
            self.toplevel, text="Cancel", command=self.cancel
        )

        self.label.pack(side=tk.LEFT, padx=5, fill="x", expand=True)
        self.help_label.pack(side=tk.RIGHT)
        self.upper_frame.pack(side=tk.TOP, padx=5)
        self.text.pack(side=tk.TOP, padx=5, fill="x", expand=True)
        self.confirm_button.pack(side=tk.RIGHT, anchor=tk.E, padx=10, pady=5)
        self.cancel_button.pack(side=tk.RIGHT, anchor=tk.W, padx=10, pady=5)
        self.confirm_cancel_frame.pack()

    def confirm(self):
        self.input_string = self.text.get(1.0, tk.END).strip()
        self.toplevel.destroy()

    def cancel(self):
        self.is_cancel = True
        self.input_string = ""
        self.toplevel.destroy()

    @classmethod
    def ask(cls, parent: tk.Tk, initial_value="") -> list[int] | Literal[False]:
        """Asks user for beats per measure pattern"""
        instance = AskBeatPattern(parent, initial_value=initial_value)
        instance.toplevel.wait_window()
        if instance.is_cancel:
            return False
        beats_per_measure = instance.input_string
        beats_per_measure = beats_per_measure.split()
        beats_per_measure = [int(m) for m in beats_per_measure]
        return beats_per_measure
