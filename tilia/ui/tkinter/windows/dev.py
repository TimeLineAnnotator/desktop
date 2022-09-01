"""
Window that enables executing python statements while the tkinter mainloop is running.
Not reimplemented yet.
"""

import tkinter as tk
import tilia.globals_ as globals_


class DevWindow(tk.Toplevel):
    def __init__(self, parent):
        super(DevWindow, self).__init__(parent)
        self.title(
            "For development only. IF YOU'RE SEEING THIS, PLEASE CONTACT DEVELOPER IMMEDIATELY"
        )
        self.frame = DevFrame(self)
        self.frame.pack(pady=5, padx=5, expand=True, fill="x")
        self.focus_set()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def on_closing(self):
        globals_.DEV_WINDOW = None
        self.destroy()


class DevFrame(tk.Frame):
    def __init__(self, parent):
        super(DevFrame, self).__init__(parent)

        dev_entry1 = tk.Text(self, width=60, height=5)
        dev_entry1.insert("1.0", globals_.EXEC_TEXT)
        dev_entry1.pack(fill="x")

        def execute_entry():
            entry_text = dev_entry1.get("1.0", tk.END)
            exec(entry_text)

        dev_button1 = tk.Button(self, command=execute_entry, text="Run")
        dev_button1.pack(padx=5, pady=5)

        canvas = globals_.TIMELINE_COLLECTION.objects[0].canvas

        entry = tk.Entry(self)
        button1 = tk.Button(
            self,
            text="Hide row",
            command=lambda: canvas.hide_row_by_index(int(entry.get())),
        )
        button2 = tk.Button(
            self,
            text="Show row",
            command=lambda: canvas.show_row_by_index(int(entry.get())),
        )

        entry.pack()
        button1.pack()
        button2.pack()
