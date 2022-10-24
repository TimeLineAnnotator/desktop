import tkinter
import tkinter as tk
import tkinter.colorchooser
import tkinter.messagebox
import tkinter.simpledialog


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


def display_error(title: str, message: str) -> None:
    tkinter.messagebox.showerror(title, message)


def ask_for_color(starting_color: str) -> str | None:
    return tk.colorchooser.askcolor(title="Choose unit color", color=starting_color)[1]


def ask_for_string(title: str, prompt: str, initialvalue: str) -> str | None:
    return tk.simpledialog.askstring(title, prompt, initialvalue=initialvalue)


def ask_for_int(title: str, prompt: str, initialvalue: int) -> int | None:
    return tk.simpledialog.askinteger(title, prompt, initialvalue=initialvalue)
