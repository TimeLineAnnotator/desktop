import tkinter as tk
from tkinter import simpledialog, messagebox, filedialog, colorchooser
from typing import Optional
import logging

from tilia import globals_
from tilia.requests import Post, post
from tilia.globals_ import APP_NAME, FILE_EXTENSION
from tilia.exceptions import UserCancel
from tilia.ui.windows.beat_pattern import AskBeatPattern

logger = logging.getLogger(__name__)


def ask_should_save_changes():
    return tk.messagebox.askyesnocancel(
        "Save changes?", "Save changes to current file?"
    )


def ask_string(title: str, prompt: str) -> str:
    return tk.simpledialog.askstring(title, prompt=prompt)


def ask_yes_no(title: str, prompt: str) -> bool:
    return tk.messagebox.askyesno(title, prompt)


def ask_for_tilia_file_to_open():
    path = tk.filedialog.askopenfilename(
        title=f"Open {APP_NAME} file...",
        filetypes=(
            (f"{APP_NAME} files", f".{FILE_EXTENSION}"),
            ("All files", "*.*"),
        ),
    )

    if not path:
        raise UserCancel("User cancelled or closed open window dialog.")

    return path


def ask_for_file_to_open(title: str, filetypes: tuple[tuple[str, str]]) -> str:
    path = tk.filedialog.askopenfilename(title=title, filetypes=filetypes)

    if not path:
        raise UserCancel("User cancelled or closed open window dialog.")

    return path


def ask_for_color(starting_color: str) -> str | None:
    return tk.colorchooser.askcolor(title="Choose unit color", color=starting_color)[1]


def ask_for_string(title: str, prompt: str, initialvalue: str = "") -> str | None:
    return tk.simpledialog.askstring(title, prompt, initialvalue=initialvalue)


def ask_for_int(
    title: str, prompt: str, initialvalue: Optional[int] = None
) -> int | None:
    return tk.simpledialog.askinteger(title, prompt, initialvalue=initialvalue)


def ask_for_float(
    title: str, prompt: str, initialvalue: Optional[float] = None
) -> float | None:
    return tk.simpledialog.askfloat(title, prompt, initialvalue=initialvalue)


def ask_for_directory(title: str) -> str | None:
    return tk.filedialog.askdirectory(title=title)


def ask_for_path_to_save_tilia_file(initial_filename: str) -> str | None:
    path = tk.filedialog.asksaveasfilename(
        defaultextension=f"{FILE_EXTENSION}",
        initialfile=initial_filename,
        filetypes=((f"{APP_NAME} files", f".{FILE_EXTENSION}"),),
    )

    if not path:
        raise UserCancel()

    if path.endswith(f"{FILE_EXTENSION}") and not path.endswith(f".{FILE_EXTENSION}"):
        path = path[:-3] + ".tla"

    return path


def ask_for_media_file():
    audio_filetypes = get_filetypes_str(
        globals_.SUPPORTED_AUDIO_FORMATS + globals_.CONVERTIBLE_AUDIO_FORMATS
    )

    video_filetypes = get_filetypes_str(globals_.SUPPORTED_VIDEO_FORMATS)

    all_filetypes = get_filetypes_str(
        globals_.SUPPORTED_AUDIO_FORMATS
        + globals_.CONVERTIBLE_AUDIO_FORMATS
        + globals_.SUPPORTED_VIDEO_FORMATS
    )

    file_path = tk.filedialog.askopenfilename(
        title="Load media...",
        filetypes=[
            ("All supported media files", all_filetypes),
            ("Audio files", audio_filetypes),
            ("Video files", video_filetypes),
            ("All files", "*.*"),
        ],
    )

    if not file_path:
        logger.debug("User cancelled or closed load media window.")
        return

    return file_path


def ask_delete_timeline(timeline_str: str) -> bool | None:
    return ask_yes_no(
        "Delete timeline",
        f"Are you sure you want to delete timeline {timeline_str}?",
    )


def ask_clear_timeline(timeline_str: str) -> bool | None:
    return tk.messagebox.askyesno(
        "Delete timeline",
        f"Are you sure you want to clear timeline {timeline_str: str}?",
    )


def ask_clear_all_timelines() -> bool | None:
    return tk.messagebox.askyesno(
        "Delete timeline",
        "Are you sure you want to clear ALL timelines?",
    )


def get_filetypes_str(formats: list):
    filetypes = ""
    for frmt in formats:
        filetypes += "." + frmt + " "

    return filetypes.rstrip()


def display_error(title: str, message: str):
    lines = message.split("\n")
    if len(lines) > 35:
        message = "\n".join(lines[:35]) + "\n..."
    tk.messagebox.showerror(title, message)


def ask_open_file_name(title: str, filetypes: list[tuple[str, str]]):
    return tk.filedialog.askopenfilename(title=title, filetypes=filetypes)


def ask_for_beat_pattern() -> list[int] | None:
    result = AskBeatPattern.ask()

    if result is False:
        return None
    elif len(result) == 0:
        post(
            Post.REQUEST_DISPLAY_ERROR,
            "Insert beat pattern",
            "Beat pattern must be one or more numbers.",
        )
        return ask_for_beat_pattern()
    else:
        return result
