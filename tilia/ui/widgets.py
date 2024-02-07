from __future__ import annotations

import tkinter as tk
from typing import Callable


class CheckboxItem(tk.Frame):
    def __init__(
        self, label: str, value: bool, set_func: Callable, parent, *args, **kwargs
    ):
        """Checkbox toolbar item to be displayed above timeline toolbars.
        value is the default boolean value of the checkbox.
        set_func is the function that will be called on checkbox change.
        set_func will be called with the checkbox itself as first parameter,
        emulating a method call (with self as first parameter)."""
        super().__init__(parent, *args, **kwargs)
        self.variable = tk.BooleanVar(value=value)
        self.checkbox = tk.Checkbutton(
            self, command=set_func, variable=self.variable, takefocus=False
        )
        self.label = tk.Label(self, text=label)

        self.checkbox.pack(side=tk.LEFT)
        self.label.pack(side=tk.LEFT)
