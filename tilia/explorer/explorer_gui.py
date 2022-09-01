from __future__ import annotations

import time
from typing import Callable, Literal, Optional

import tilia.globals_ as globals_

import tkinter as tk

# noinspection PyPep8Naming
import tkinter.font as tkFont
import tkinter.ttk as ttk

import tilia.events as events
import tilia.player.player_ui as player_ui
from tilia.explorer.explorer_types import MeasureLength

TIMELINE_TYPES = ["Hierarchy"]
SEARCH_MODE = ["ANY", "ALL"]

FILE_SEARCH_ATTRS = [
    ("title", str),
    ("composer", str),
    ("tonality", str),
    ("form", str),
    ("time_signature", str),
]

SEARCH_ATTRS_TO_DISPLAY_STRING = {
    # timeline objects attrs
    "start": "start",
    "end": "end",
    "label": "label",
    "level": "level",
    "formal_type": "formal type",
    "formal_function": "formal function",
    "measure_start": "start (bar.beat)",
    "measure_end": "end (bar.beat)",
    "measure_length": "length (bar.beat)",
    "comments": "comments",
    # file attrs
    "title": "title",
    "composer": "composer",
    "tonality": "tonality",
    "form": "form",
    "time_signature": "time signature",
    # other attrs
    "timeline": "timeline",
}

DISPLAY_NAME_TO_TIMELINETYPE = {"Hierarchy": "HierarchyTimeline"}

TLOBJS_SEARCH_ATTRS = {
    "Hierarchy": [
        ("start", float),
        ("end", float),
        ("label", str),
        ("level", int),
        ("formal_type", str),
        ("formal_function", str),
        ("measure_start", MeasureLength),
        ("measure_end", MeasureLength),
        ("measure_length", MeasureLength),
        ("comments", str),
    ]
}

TLOBJS_SEARCH_VALIDATORS = {
    str: lambda: True,
    int: lambda: True,
    float: lambda: True,
    MeasureLength: lambda: True,
}

FILE_SEARCH_VALIDATORS = {str: lambda: True}

# tuple of the form (operator, negate, inclusive)
OPERATORS_TO_PARAMS: dict[str : tuple[str, Optional[bool]]] = {
    "<": ("SMALLER", False, False),
    "<=": ("SMALLER", False, True),
    ">": ("GREATER", False, False),
    ">=": ("GREATER", False, True),
    "=": ("EQUALS", False),
    "contain(s)": ("CONTAINS", False),
}

SEARCHTYPE_TO_OPERATORS = {
    str: ["=", "contain(s)"],
    float: ["<", "<=", ">", ">=", "="],
    int: ["<", "<=", ">", ">=", "="],
    MeasureLength: ["<", "<=", ">", ">=", "="],
}

DEFAULT_FILEDIR_PATH = (
    "C:\Música e musicologia\Outros\Sonatas do Mozart\Análises para o artigo"
)


def convert_conditions_to_params(
    file_conditions: list[tuple[str, str, str]]
) -> tuple[str, str, str, Optional[bool]]:

    params = []
    for condition in file_conditions:
        params.append(
            (
                get_attr_by_displayname(condition[0]),
                condition[1],
                *OPERATORS_TO_PARAMS[condition[2]],
            )
        )

    # noinspection PyTypeChecker
    return params


class ExplorerGUI:
    pass


class ExplorerTkGUI(events.Subscriber, ExplorerGUI):
    ADD_CONDITION_BUTTON_TEXT = "Add..."
    SEARCH_BUTTON_TEXT = "Search..."
    COLUMN_ORDER = [
        "title",
        "form",
        "tonality",
        "timeline",
        "start",
        "end",
        "label",
        "level",
        "formal_type",
        "formal_function",
        "measure_start",
        "measure_end",
        "measure_length",
        "comments",
    ]

    FILE_DATA_TO_ADD = ["title", "form", "tonality", "time_signature"]

    DEFAULT_FILE_CONDITIONS = []
    DEFAULT_TLOBJECTS_CONDITIONS = [("end", "<", "15"), ("level", "=", "2")]

    def __init__(self, parent: tk.Tk | tk.Toplevel):
        super().__init__(["EXPLORER: DISPLAY SEARCH RESULTS"])
        self._setup_widgets(parent)
        self.tlobjects_condition_frames = []
        self.file_condition_frames = []

        self.insert_default_conditions()

    def _setup_widgets(self, parent: tk.Tk | tk.Toplevel) -> None:
        self.frame = tk.Frame(parent)

        self.main_options_frame = tk.Frame(self.frame)
        self.file_conditions_metaframe = tk.LabelFrame(
            self.frame, text="File conditions"
        )
        self.add_file_condition_button = tk.Button(
            self.file_conditions_metaframe,
            text=self.ADD_CONDITION_BUTTON_TEXT,
            command=lambda: self.insert_search_condition("file"),
        )
        self.tlobjects_conditions_metaframe = tk.LabelFrame(
            self.frame, text="Timeline objects conditions"
        )
        self.add_tlobjects_condition_button = tk.Button(
            self.tlobjects_conditions_metaframe,
            text=self.ADD_CONDITION_BUTTON_TEXT,
            command=lambda: self.insert_search_condition("timeline_object"),
        )
        self.bottom_buttons_frame = tk.Frame(self.frame)

        self.filedir_label = tk.Label(self.main_options_frame, text="Folder to search:")
        self.filedir_entry = tk.Entry(self.main_options_frame)
        self.filedir_entry.insert(1, DEFAULT_FILEDIR_PATH)

        self.timeline_type_label = tk.Label(
            self.main_options_frame, text="Timeline type:"
        )
        self.timeline_type_var = tk.StringVar()
        self.timeline_type_optionmenu = ttk.OptionMenu(
            self.main_options_frame,
            self.timeline_type_var,
            TIMELINE_TYPES[0],
            *TIMELINE_TYPES,
        )

        self.match_mode_label = tk.Label(self.main_options_frame, text="Match mode:")
        self.match_mode_var = tk.StringVar()
        self.match_mode_optionmenu = ttk.OptionMenu(
            self.main_options_frame, self.match_mode_var, SEARCH_MODE[0], *SEARCH_MODE
        )

        self.search_button = tk.Button(
            self.bottom_buttons_frame,
            text=self.SEARCH_BUTTON_TEXT,
            command=self.request_search,
        )

        self.main_options_frame.pack(fill="x", padx=3, pady=3)
        self.file_conditions_metaframe.pack(fill="x", padx=3, pady=3)
        self.tlobjects_conditions_metaframe.pack(fill="x", padx=3, pady=3)
        self.bottom_buttons_frame.pack(fill="x", padx=3, pady=3)

        self.filedir_label.grid(row=0, column=0)
        self.filedir_entry.grid(row=0, column=1, sticky="ew")
        self.timeline_type_label.grid(row=1, column=0)
        self.timeline_type_optionmenu.grid(row=1, column=1, sticky="ew")
        self.match_mode_label.grid(row=2, column=0)
        self.match_mode_optionmenu.grid(row=2, column=1, sticky="ew")

        self.main_options_frame.grid_columnconfigure(1, weight=1)

        self.add_file_condition_button.pack(side="bottom", anchor="w")
        self.add_tlobjects_condition_button.pack(side="bottom", anchor="w")

        self.search_button.pack(padx=3, pady=3)

    def pack(self, *args, **kwargs):
        self.frame.pack(*args, **kwargs)

    def insert_default_conditions(self):
        for condition in self.DEFAULT_FILE_CONDITIONS:
            self.insert_search_condition("file", condition)
        for condition in self.DEFAULT_TLOBJECTS_CONDITIONS:
            self.insert_search_condition("timeline_object", condition)

    def insert_search_condition(
        self,
        search_type: Literal["file", "timeline_object"],
        initial_values: Optional[tuple[str, str, str]] = None,
    ):

        tl_type = self.timeline_type_var.get()

        if search_type == "timeline_object":
            search_attrs_tuple = TLOBJS_SEARCH_ATTRS[tl_type]
            search_validators = TLOBJS_SEARCH_VALIDATORS
            condition_metaframe = self.tlobjects_conditions_metaframe
            condition_frame_list = self.tlobjects_condition_frames
        elif search_type == "file":
            search_attrs_tuple = FILE_SEARCH_ATTRS
            search_validators = FILE_SEARCH_VALIDATORS
            condition_metaframe = self.file_conditions_metaframe
            condition_frame_list = self.file_condition_frames
        else:
            raise ValueError(f"Invalid search type '{search_type}'")

        attrs = [SEARCH_ATTRS_TO_DISPLAY_STRING[attr[0]] for attr in search_attrs_tuple]
        operators = {
            attr[0]: SEARCHTYPE_TO_OPERATORS[attr[1]] for attr in search_attrs_tuple
        }
        validators = {
            attr[0]: TLOBJS_SEARCH_VALIDATORS[attr[1]] for attr in search_attrs_tuple
        }

        new_condition_frame = ConditionFrame(
            condition_metaframe, attrs, operators, validators, self
        )

        condition_frame_list.append(new_condition_frame)
        new_condition_frame.pack(anchor="w", padx=3, pady=3)

        if initial_values:
            new_condition_frame.set_values(*initial_values)

    def remove_condition(self, condition: ConditionFrame):
        if condition in self.tlobjects_condition_frames:
            self.tlobjects_condition_frames.remove(condition)
        else:
            self.file_condition_frames.remove(condition)

    def request_search(self):
        file_conditions = self.get_search_conditions("file")
        tlobjects_conditions = self.get_search_conditions("timeline_object")

        events.post(
            "EXPLORER: SEARCH",
            self.filedir_entry.get(),
            convert_conditions_to_params(file_conditions),
            self.match_mode_var.get(),
            DISPLAY_NAME_TO_TIMELINETYPE[self.timeline_type_var.get()],
            convert_conditions_to_params(tlobjects_conditions),
            self.match_mode_var.get(),
            self.COLUMN_ORDER,
            self.FILE_DATA_TO_ADD,
        )

    def get_search_conditions(self, condition_type: Literal["file", "timeline_object"]):
        if condition_type == "file":
            cdt_frame_list = self.file_condition_frames
        elif condition_type == "timeline_object":
            cdt_frame_list = self.tlobjects_condition_frames
        else:
            raise ValueError(f"Invalid condition type '{condition_type}'")

        return [cdt_frame.get_conditions() for cdt_frame in cdt_frame_list]

    def on_subscribed_event(self, event_name: str, args: tuple, kwargs: dict) -> None:
        if event_name == "EXPLORER: DISPLAY SEARCH RESULTS":
            df = args[0]

            df["start"] = df["start"].map(
                lambda x: time.strftime("%M:%S", time.gmtime(x))
            )
            df["end"] = df["end"].map(lambda x: time.strftime("%M:%S", time.gmtime(x)))
            ExplorerResultsWindow(
                list(df), list(df.itertuples(index=False)), df.index.values.tolist()
            )


def get_attr_by_displayname(displayname: str) -> str:
    return next(
        key
        for key, value in SEARCH_ATTRS_TO_DISPLAY_STRING.items()
        if value == displayname
    )


class ConditionFrame(tk.Frame):
    ATTR_OPTIONMENU_WIDTH = 15
    OPERATOR_OPTIONMENU_WIDTH = 8
    DELETE_BUTTON_TEXT = "❌"
    DELETE_BUTTON_WIDTH = 2

    def __init__(
        self,
        parent: tk.Frame | tk.LabelFrame,
        attr_values: list[str],
        operator_values: dict[str, list[str]],
        search_value_validator: dict[str, Callable],
        search_interface: ExplorerTkGUI,
    ):

        super().__init__(parent)
        self.search_interface = search_interface
        self.operator_values = operator_values
        self.search_value_validator = search_value_validator
        self._setup_widgets(attr_values)

    def _setup_widgets(self, attr_values: list[str]) -> None:
        self.attr_var = tk.StringVar()

        self.attr_optionmenu = ttk.OptionMenu(
            self, self.attr_var, attr_values[0], *attr_values
        )
        self.attr_optionmenu.config(width=self.ATTR_OPTIONMENU_WIDTH)
        self.operator_var = tk.StringVar()
        self.operator_optionmenu = ttk.OptionMenu(
            self,
            self.operator_var,
            self.operator_values[attr_values[0]][0],
            *self.operator_values[attr_values[0]],
        )
        self.operator_optionmenu.config(width=self.OPERATOR_OPTIONMENU_WIDTH)
        self.value_var = tk.StringVar()
        self.value_entry = tk.Entry(self)

        self.delete_button = tk.Button(
            self,
            text=self.DELETE_BUTTON_TEXT,
            width=self.DELETE_BUTTON_WIDTH,
            command=self.remove,
        )

        self.attr_optionmenu.pack(side="left")
        self.operator_optionmenu.pack(side="left")
        self.value_entry.pack(side="left")
        self.delete_button.pack(side="left", padx=3)

        self.attr_var.trace_add("write", self.change_operator_options)

    def change_operator_options(self, *_):
        new_attr = get_attr_by_displayname(self.attr_var.get())
        new_operators = self.operator_values[new_attr]
        self.operator_optionmenu.set_menu(new_operators[0], *new_operators)

    def get_conditions(self):
        return self.attr_var.get(), self.value_entry.get(), self.operator_var.get()

    def remove(self):
        self.search_interface.remove_condition(self)
        self.destroy()

    def set_values(self, attr: str, operator: str, search_value: str):
        self.attr_var.set(attr)
        self.operator_var.set(operator)
        self.value_entry.delete(0, "end")
        self.value_entry.insert(0, search_value)


class ExplorerResultsWindow(tk.Toplevel):
    MAX_COLUMN_WIDTH = 150
    WIDTH = 800

    def __init__(self, headers: list[str], values: list[tuple], indexes: list[str]):
        super().__init__()
        self.config(width=self.WIDTH)
        self.title(f"{globals_.APP_NAME} Explorer - search results")
        self.headers = headers
        self.values = values
        self.indexes = indexes
        self.tree = None
        self._setup_widgets()
        self._build_tree()

    def _setup_widgets(self):
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True)

        # create treeview
        self.tree = ttk.Treeview(tree_frame, columns=self.headers, show="headings")
        vertical_scrollbar = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview
        )
        horizontal_scrollbar = ttk.Scrollbar(
            tree_frame, orient="horizontal", command=self.tree.xview
        )
        self.tree.configure(
            yscrollcommand=vertical_scrollbar.set,
            xscrollcommand=horizontal_scrollbar.set,
        )
        self.tree.grid(column=0, row=0, sticky="nsew")
        vertical_scrollbar.grid(column=1, row=0, sticky="ns")
        horizontal_scrollbar.grid(column=0, row=1, sticky="ew")
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        self.tree.bind("<ButtonRelease-1>", self.on_click)

        # create player
        player_frame = player_ui.PlayerUI(self)
        player_frame.pack(padx=5, pady=5)

    def on_click(self, event: tk.Event):
        region = self.tree.identify("region", event.x, event.y)
        if not region == "heading":
            item = self.tree.focus()
            events.post(events.EventName.EXPLORER_LOAD_MEDIA, self.tree.item(item, "text"))

    def _build_tree(self) -> None:
        for col in self.headers:
            self.tree.heading(
                col,
                text=SEARCH_ATTRS_TO_DISPLAY_STRING[col.title().lower()].capitalize(),
            )
            # adjust the column's width to the header string
            self.tree.column(col, width=tkFont.Font().measure(col.title()))

        for index, item in enumerate(self.values):
            self.tree.insert("", "end", values=item, text=self.indexes[index])
            # adjust column's width if necessary to fit each value
            for index2, val in enumerate(item):
                col_w = min(tkFont.Font().measure(val), self.MAX_COLUMN_WIDTH)

                if self.tree.column(self.headers[index2], option="width") < col_w:
                    self.tree.column(self.headers[index2], width=col_w)
