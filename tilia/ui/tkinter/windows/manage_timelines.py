
class ManageTimelines(tk.Toplevel, Unique):
    def __init__(self, items: list, update_action: Callable):
        """
        Window with options to change order, toggle visibility
        and delete timelines.
        """
        LOGGER.info("Creating ManageTimelines.")
        if not items:
            app_globals.APP.display_error(
                "No timelines to manage. Add some timelines via Timelines > Add..."
            )
            return
        Unique.__init__(self)
        tk.Toplevel.__init__(self)

        # defaults for AppWindow, can't import due to circular dependency
        self.transient(app_globals.APP.parent)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.title("Timeline settings")

        self.items = items
        self.update_action = update_action
        self.outer_frame = tk.Frame(self)

        # right frame creation
        self.right_frame = tk.Frame(self.outer_frame)
        self.up_button = tk.Button(
            self.right_frame, text="▲", width=3, command=self.move_up
        )
        self.down_button = tk.Button(
            self.right_frame, text="▼", width=3, command=self.move_down
        )
        self.delete_button = tk.Button(
            self.right_frame, text="Delete", command=self.ask_delete_timeline
        )
        self.clear_button = tk.Button(
            self.right_frame, text="Clear", command=self.ask_clear_timeline
        )

        # checkbox creation
        self.visible_checkbox_var = tk.BooleanVar()
        self.visible_checkbox = tk.Checkbutton(
            self.right_frame,
            text="Visible",
            variable=self.visible_checkbox_var,
            onvalue=True,
            offvalue=False,
            command=self.on_checkbox,
        )

        # element griding and packing
        self.up_button.grid(column=1, row=0, sticky=tk.EW)
        self.down_button.grid(column=1, row=1, sticky=tk.EW)
        self.visible_checkbox.grid(column=1, row=2, sticky=tk.EW)
        self.delete_button.grid(column=1, row=3, sticky=tk.EW)
        self.clear_button.grid(column=1, row=4, sticky=tk.EW)

        self.list_box = tk.Listbox(self.outer_frame, width=40, activestyle="none")
        self.list_box.insert("end", *self.items)

        self.scrollbar = tk.Scrollbar(self.outer_frame, orient=tk.VERTICAL)
        self.scrollbar.config(command=self.list_box.yview)
        self.list_box.config(yscrollcommand=self.scrollbar.set)

        self.right_frame.pack(expand=tk.YES, fill=tk.BOTH, side=tk.RIGHT)
        self.list_box.pack(expand=True, side=tk.LEFT)
        self.scrollbar.pack(expand=True, fill=tk.BOTH, side=tk.LEFT)

        self.grid_columnconfigure(0, weight=1)
        self.outer_frame.pack(expand=True)

        # element binding
        self.list_box.bind("<<ListboxSelect>>", self.on_select)

        # setting initial focus and default values
        self.initial_config()

    def initial_config(self) -> None:
        """Set focus to window and select first element"""
        self.list_box.focus_set()
        self.list_box.select_set(0)
        self.on_select()

    def on_select(self, _=None):
        """Updates checkbox to reflect visibility status of the selected timeline"""
        item = self.list_box.get(self.list_box.curselection())
        index = self.list_box.index(self.list_box.curselection())
        LOGGER.debug(f"Selected {item} at index {index}")
        is_vsbl = app_globals.APP.timeline_collection.find_by_collection_id(
            item[2]
        ).visible
        if is_vsbl:
            self.visible_checkbox.select()
        else:
            self.visible_checkbox.deselect()

    def on_checkbox(self):
        """Toggles visibility of selected timeline"""
        checkbox_value = self.visible_checkbox_var.get()
        i = int(self.list_box.curselection()[0])
        timeline_id = self.list_box.get(i)[2]

        if checkbox_value:
            app_globals.APP.timeline_collection.find_by_collection_id(
                timeline_id
            ).make_visible()
        else:
            app_globals.APP.timeline_collection.find_by_collection_id(
                timeline_id
            ).make_invisible()

    def move_up(self):
        """Move timeline up"""
        item = self.list_box.get(self.list_box.curselection())
        index = self.list_box.index(self.list_box.curselection())
        LOGGER.info(f"Moving {item[2]} up.")
        if index == 0:
            pass  # already at top
        else:
            self.list_box.delete(self.list_box.curselection())
            self.list_box.insert(index - 1, item)
            self.list_box.activate(index - 1)
            self.list_box.select_set(index - 1)

        self.sort_list()
        self.update_action()

    def move_down(self):
        """Move timeline down"""
        item = self.list_box.get(self.list_box.curselection())
        index = self.list_box.index(self.list_box.curselection())
        LOGGER.info(f"Moving {item[2]} down.")
        if index == self.list_box.index("end") - 1:
            pass  # already at bottom
        else:
            self.list_box.delete(self.list_box.curselection())
            self.list_box.insert(index + 1, item)
            self.list_box.activate(index + 1)
            self.list_box.select_set(index + 1)

        self.sort_list()
        self.update_action()

    def sort_list(self):
        self.items = self.list_box.get(0, "end")

    def ask_delete_timeline(self):
        item = self.list_box.get(self.list_box.curselection())
        index = self.list_box.index(self.list_box.curselection())
        timeline_id = self.list_box.get(index)[2]
        if messagebox.askquestion(
                "Delete timeline", f"Are you sure you want to delete timeline {item}?"
        ) == 'yes':
            app_globals.APP.timeline_collection.remove_by_id(timeline_id)
        self.list_box.delete(index)
        self.initial_config()

    def ask_clear_timeline(self):
        item = self.list_box.get(self.list_box.curselection())
        index = self.list_box.index(self.list_box.curselection())
        timeline_id = self.list_box.get(index)[2]
        if messagebox.askquestion(
                "Delete timeline", f"Are you sure you want to clear timeline {item}?"
        ) == 'yes':
            app_globals.APP.timeline_collection.clear_by_id(timeline_id)

    def on_close(self):
        Unique.delete(self)
        self.destroy()