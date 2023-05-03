import tkinter as tk

from tilia.ui.dialogs.tilia_dialog import TiliaDialog


class ByTimeOrByMeasure(TiliaDialog):
    def __init__(self, parent):
        super().__init__(parent, title="Import makers from .csv")
        self.var = tk.StringVar()

        self._toplevel.geometry("300x110")

        self.prompt = tk.Label(self._toplevel, text="Import using:")
        self.radio_frame = tk.Frame(self._toplevel)
        self.radio_time = tk.Radiobutton(
            self.radio_frame, text="Time", variable=self.var, value="time"
        )
        self.radio_measure = tk.Radiobutton(
            self.radio_frame,
            text="Measure and fraction",
            variable=self.var,
            value="measure",
        )

        self.prompt.pack()
        self.radio_frame.pack()
        self.radio_time.pack()
        self.radio_measure.pack()

        self.var.set("time")

    def get_return_value(self):
        return self.var.get()
