import enum
import tkinter
import tkinter as tk
import tkinter.messagebox

from tilia import events
from tilia.events import EventName


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


class RightClickMenuOptions(enum.Enum):
    SEPARATOR = 'SEPARATOR'


def display_right_click_menu(x: int, y: int, options: list[str]) -> None:
    class RightClickMenu:
        def __init__(
                self,
                x: int,
                y: int,
                options: list[str]
        ):
            self.tk_menu = tk.Menu(tearoff=False)
            self.register_options(options)
            self.tk_menu.tk_popup(x, y)

        def register_options(self, options: list[str]):
            for option in options:
                if option == RightClickMenuOptions.SEPARATOR:
                    self.tk_menu.add_separator()
                else:
                    self.tk_menu.add_command(
                        label=option,
                        command=lambda _option=option: events.post(EventName.RIGHT_CLICK_MENU_OPTION_CLICK, _option)
                    )

    RightClickMenu(x, y, options)
