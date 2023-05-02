import tkinter as tk

from .tilia_dialog import TiliaDialog


class ChooseDialog(TiliaDialog):

    NON_EDITABLE_FIELDS = ["media path", "audio length"]
    SEPARATE_WINDOW_FIELDS = ["notes"]

    def __init__(
        self,
        parent: tk.Tk | tk.Toplevel,
        title: str,
        prompt: str,
        options: list[tuple[int, str]],
        *args,
        **kwargs
    ) -> None:

        super().__init__(parent, title, width=400)
        self.prompt_text = prompt
        self.options = options
        self.return_value = None

        self.setup_widgets()

    # noinspection PyAttributeOutsideInit
    def setup_widgets(self):
        self.prompt_label = tk.Label(self._toplevel, text=self.prompt_text)
        self.list_box = tk.Listbox(self._toplevel)
        self.list_box.insert(0, *[opt[1] for opt in self.options])
        self.list_box.activate(0)

        self.prompt_label.pack(side=tk.TOP)
        self.list_box.pack(side=tk.TOP)

    def get_selected_index(self) -> tuple[int]:
        return self.list_box.curselection()[0]

    def get_return_value(self):
        return self.options[self.get_selected_index()][0]
