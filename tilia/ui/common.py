import tkinter
import tkinter as tk
import tkinter.colorchooser
import tkinter.messagebox
import tkinter.simpledialog
import tkinter.filedialog


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


def destroy_children_recursively(widget: tk.Widget | tk.Toplevel) -> None:
    """Recursively destroys all children of 'widget'"""
    children = widget.winfo_children()

    for item in children:
        if item.winfo_children():
            children.extend(item.winfo_children())

    for child in children:
        child.destroy()


def format_media_time(audio_time: float | str) -> str:
    minutes = str(int(float(audio_time) // 60)).zfill(2)
    seconds_and_fraction = f"{audio_time % 60:.1f}".zfill(4)
    return f"{minutes}:{seconds_and_fraction}"
