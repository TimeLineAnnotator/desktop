import tkinter as tk


class ChooseWindow:

    NON_EDITABLE_FIELDS = ["media path", "audio length"]
    SEPARATE_WINDOW_FIELDS = ["notes"]

    def __init__(self, title: str, prompt: str, options: list[tuple[int, str]]) -> None:

        self._toplevel = tk.Toplevel(width=400)
        self._toplevel.title(title)
        self._toplevel.protocol("WM_DELETE_WINDOW", self.on_cancel)
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

        self.button_frame = tk.Frame(self._toplevel)
        self.ok_button = tk.Button(self.button_frame, text="OK", command=self.on_ok)
        self.cancel_button = tk.Button(
            self.button_frame, text="Cancel", command=self.on_cancel
        )

        self.prompt_label.pack()
        self.list_box.pack()
        self.button_frame.pack()
        self.ok_button.pack(side=tk.RIGHT)
        self.cancel_button.pack(side=tk.LEFT)

    def get_selected_index(self) -> tuple[int]:
        return self.list_box.curselection()[0]

    def on_ok(self):
        self.return_value = self.options[self.get_selected_index()][0]
        self.destroy()

    def on_cancel(self):
        self.return_value = False
        self.destroy()

    def ask(self):
        self._toplevel.wait_window()
        return self.return_value

    def destroy(self):
        self._toplevel.destroy()
