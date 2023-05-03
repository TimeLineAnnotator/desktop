import tkinter as tk
from abc import ABC, abstractmethod


class TiliaDialog(ABC):
    """
    To be inherited by concrete dialogs. User the ask() method to ask for user input.
    Dialog result will be stored in the return_value attribute. Result will be False if
    the user cancelled, and None if the user closed the dialog.

    """

    def __init__(self, parent, title: str, *args, **kwargs) -> None:
        self._toplevel = tk.Toplevel(parent, *args, **kwargs)
        self._toplevel.title(title)
        self._toplevel.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self._toplevel.resizable(False, False)
        self._toplevel.transient(parent)
        self.return_value = None

        self.button_frame = tk.Frame(self._toplevel)
        self.ok_button = tk.Button(self.button_frame, text="OK", command=self.on_ok)
        self.cancel_button = tk.Button(
            self.button_frame, text="Cancel", command=self.on_cancel
        )

        self.button_frame.pack(side=tk.BOTTOM, padx=10, pady=10)
        self.ok_button.pack(side=tk.RIGHT, padx=10)
        self.cancel_button.pack(side=tk.LEFT)

    @abstractmethod
    def get_return_value(self):
        ...

    def on_ok(self):
        self.return_value = self.get_return_value()
        self.destroy()

    def on_cancel(self):
        self.return_value = False
        self.destroy()

    def ask(self):
        self._toplevel.wait_window()
        return self.return_value

    def destroy(self):
        self._toplevel.destroy()
