import tkinter as tk


class LabelAndEntry(tk.Frame):
    """Create a tk.Label(), tk.Entry() pair with an associated tk.StrVar()"""

    width = 32

    def __init__(self, parent, label, attr_to_link=None):
        super(LabelAndEntry, self).__init__(parent)
        label_text = label + ":"
        self.label = tk.Label(parent, text=label_text)

        self.entry = tk.Entry(parent)
        self.entry_var = tk.StringVar()
        self.entry.config(textvariable=self.entry_var)

        self.linked_attr = attr_to_link


class LabelAndLabel(tk.Frame):
    """Create a tk.Label() pair and grid them side on row 0 of
    widget 'parent'."""

    def __init__(self, parent, title, row, column=0, value=""):
        super(LabelAndLabel, self).__init__(parent)
        label_text = title + ":"
        self.label = tk.Label(self, text=label_text)
        self.label.grid(row=0, column=0, sticky="W")
        self.label2 = tk.Label(self, text=value, anchor="w")
        self.label2.grid(row=0, column=1, sticky="EW")
        self.entry_txt = ""
