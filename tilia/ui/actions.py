from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any, Optional

from tilia.requests.post import post, Post

from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtGui import QAction, QKeySequence, QIcon


class TiliaAction(Enum):
    AUTOSAVES_FOLDER_OPEN = auto()
    HARMONY_IMPORT_FROM_CSV = auto()
    MODE_ADD = auto()
    MODE_DELETE = auto()
    HARMONY_TIMELINE_HIDE_KEYS = auto()
    HARMONY_TIMELINE_SHOW_KEYS = auto()
    HARMONY_DISPLAY_AS_ROMAN_NUMERAL = auto()
    HARMONY_DISPLAY_AS_CHORD_SYMBOL = auto()
    TIMELINE_ELEMENT_EDIT = auto()
    TIMELINES_ADD_HARMONY_TIMELINE = auto()
    HARMONY_DELETE = auto()
    HARMONY_ADD = auto()
    MEDIA_LOAD_YOUTUBE = auto()
    HIERARCHY_IMPORT_FROM_CSV = auto()
    MARKER_IMPORT_FROM_CSV = auto()
    BEAT_IMPORT_FROM_CSV = auto()
    HIERARCHY_ADD_POST_END = auto()
    HIERARCHY_ADD_PRE_START = auto()
    ABOUT_WINDOW_OPEN = auto()
    BEAT_ADD = auto()
    BEAT_DELETE = auto()
    BEAT_DISTRIBUTE = auto()
    BEAT_RESET_MEASURE_NUMBER = auto()
    BEAT_SET_AMOUNT_IN_MEASURE = auto()
    BEAT_SET_MEASURE_NUMBER = auto()
    EDIT_REDO = auto()
    EDIT_UNDO = auto()
    FILE_NEW = auto()
    FILE_OPEN = auto()
    FILE_SAVE = auto()
    FILE_SAVE_AS = auto()
    HIERARCHY_CREATE_CHILD = auto()
    HIERARCHY_DECREASE_LEVEL = auto()
    HIERARCHY_DELETE = auto()
    HIERARCHY_GROUP = auto()
    HIERARCHY_INCREASE_LEVEL = auto()
    HIERARCHY_MERGE = auto()
    TIMELINE_ELEMENT_PASTE_COMPLETE = auto()
    HIERARCHY_SPLIT = auto()
    MARKER_ADD = auto()
    MARKER_DELETE = auto()
    MEDIA_LOAD_LOCAL = auto()
    MEDIA_STOP = auto()
    MEDIA_TOGGLE_PLAY_PAUSE = auto()
    METADATA_WINDOW_OPEN = auto()
    SETTINGS_WINDOW_OPEN = auto()
    TIMELINES_AUTO_SCROLL_ENABLE = auto()
    TIMELINES_AUTO_SCROLL_DISABLE = auto()
    TIMELINES_CLEAR = auto()
    TIMELINES_ADD_BEAT_TIMELINE = auto()
    TIMELINES_ADD_HIERARCHY_TIMELINE = auto()
    TIMELINES_ADD_MARKER_TIMELINE = auto()
    TIMELINE_ELEMENT_COLOR_SET = auto()
    TIMELINE_ELEMENT_COLOR_RESET = auto()
    TIMELINE_ELEMENT_COPY = auto()
    TIMELINE_ELEMENT_DELETE = auto()
    TIMELINE_ELEMENT_INSPECT = auto()
    TIMELINE_ELEMENT_PASTE = auto()
    TIMELINE_ELEMENT_EXPORT_AUDIO = auto()
    TIMELINE_HEIGHT_SET = auto()
    TIMELINE_NAME_SET = auto()
    TIMELINE_ORDINAL_DECREASE = auto()
    TIMELINE_ORDINAL_INCREASE = auto()
    VIEW_ZOOM_IN = auto()
    VIEW_ZOOM_OUT = auto()
    WEBSITE_HELP_OPEN = auto()
    WINDOW_MANAGE_TIMELINES_OPEN = auto()
    INSPECT_WINDOW_CLOSE = auto()


@dataclass
class ActionParams:
    request: Post
    text: str
    icon: str
    shortcut: str
    args: Optional[Any] = None
    kwargs: Optional[dict[str, Any]] = None


def setup_actions(parent: QMainWindow):
    for action in TiliaAction:
        qaction = setup_action(action, parent)
        _taction_to_qaction[action] = qaction


def setup_action(action: TiliaAction, parent: QMainWindow):
    params = taction_to_params[action]
    qaction = QAction(parent)
    set_text(qaction, params.text)
    set_request(qaction, params.request, params.args, params.kwargs)
    set_action_icon(qaction, params.icon)
    qaction.setIconVisibleInMenu(False)
    set_shortcut(qaction, params.shortcut)
    set_tooltip(qaction, params.text, params.shortcut)
    return qaction


def get_img_path(basename: str):
    return Path("ui", "img", f"{basename}.png")


def set_request(
    action: QAction,
    request: Post,
    args: Optional[Any],
    kwargs: Optional[dict[str, Any]],
):
    args = args or []
    kwargs = kwargs or {}
    callback = _get_request_callback(request, args, kwargs)
    action.triggered.connect(callback)


def _get_request_callback(request: Post, args: tuple[Any], kwargs: dict[str, Any]):
    if args or kwargs:

        def callback():
            post(request, *args, **kwargs)

    else:

        def callback():
            post(request)

    return callback


def set_action_icon(action: QAction, icon: str | None):
    if icon:
        action.setIcon(QIcon(str(get_img_path(icon))))


def set_shortcut(action: QAction, shortcut: str | None):
    if shortcut:
        action.setShortcut(QKeySequence(shortcut))


def set_text(action: QAction, text: str):
    action.setText(text)


def set_tooltip(action: QAction, text: str, shortcut: str):
    action.setToolTip(f"{text} ({shortcut})" if shortcut else text)


taction_to_params = {
    TiliaAction.UI_CLOSE: ActionParams(Post.UI_CLOSE, "Close tilia", "Close", ""),
    TiliaAction.BEAT_ADD: ActionParams(
        Post.BEAT_ADD, "Add beat at current position", "beat_add", "b"
    ),
    TiliaAction.BEAT_DELETE: ActionParams(
        Post.BEAT_DELETE, "Delete", "beat_delete", ""
    ),
    TiliaAction.BEAT_DISTRIBUTE: ActionParams(
        Post.BEAT_DISTRIBUTE, "Distribute", "beat_distribute", ""
    ),
    TiliaAction.BEAT_SET_MEASURE_NUMBER: ActionParams(
        Post.BEAT_SET_MEASURE_NUMBER, "Set measure number", "beat_set_number", ""
    ),
    TiliaAction.BEAT_RESET_MEASURE_NUMBER: ActionParams(
        Post.BEAT_RESET_MEASURE_NUMBER, "Reset measure number", "beat_reset_number", ""
    ),
    TiliaAction.BEAT_SET_AMOUNT_IN_MEASURE: ActionParams(
        Post.BEAT_SET_AMOUNT_IN_MEASURE, "Set beat amount in measure", "", ""
    ),
    TiliaAction.BEAT_IMPORT_FROM_CSV: ActionParams(
        Post.BEAT_IMPORT_FROM_CSV, "Import from CSV file", "", ""
    ),
    TiliaAction.MARKER_ADD: ActionParams(
        Post.MARKER_ADD, "Add marker at current position", "add_marker30", "m"
    ),
    TiliaAction.MARKER_DELETE: ActionParams(
        Post.MARKER_DELETE, "Delete", "delete_marker30", ""
    ),
    TiliaAction.MARKER_IMPORT_FROM_CSV: ActionParams(
        Post.MARKER_IMPORT_FROM_CSV, "Import from CSV file", "", ""
    ),
    TiliaAction.TIMELINE_ELEMENT_COLOR_SET: ActionParams(
        Post.TIMELINE_ELEMENT_COLOR_SET, "Change color", "", ""
    ),
    TiliaAction.TIMELINE_ELEMENT_COLOR_RESET: ActionParams(
        Post.TIMELINE_ELEMENT_COLOR_RESET, "Reset color", "", ""
    ),
    TiliaAction.HIERARCHY_SPLIT: ActionParams(
        Post.HIERARCHY_SPLIT, "Split unit at current position", "split30", "s"
    ),
    TiliaAction.HIERARCHY_MERGE: ActionParams(
        Post.HIERARCHY_MERGE, "Merge hierarchies", "merge30", "e"
    ),
    TiliaAction.HIERARCHY_GROUP: ActionParams(
        Post.HIERARCHY_GROUP, "Group hierarchies", "group30", "g"
    ),
    TiliaAction.HIERARCHY_INCREASE_LEVEL: ActionParams(
        Post.HIERARCHY_INCREASE_LEVEL, "Increase level", "lvlup30", "Ctrl+Up"
    ),
    TiliaAction.HIERARCHY_DECREASE_LEVEL: ActionParams(
        Post.HIERARCHY_DECREASE_LEVEL, "Decrease level", "lvldwn30", "Ctrl+Down"
    ),
    TiliaAction.HIERARCHY_CREATE_CHILD: ActionParams(
        Post.HIERARCHY_CREATE_CHILD, "Create child", "below30", ""
    ),
    TiliaAction.HIERARCHY_ADD_PRE_START: ActionParams(
        Post.HIERARCHY_ADD_PRE_START, "Add pre-start", "", ""
    ),
    TiliaAction.HIERARCHY_ADD_POST_END: ActionParams(
        Post.HIERARCHY_ADD_POST_END, "Add post-end", "", ""
    ),
    TiliaAction.TIMELINE_ELEMENT_PASTE_COMPLETE: ActionParams(
        Post.TIMELINE_ELEMENT_PASTE_COMPLETE,
        "Paste complete",
        "paste_with_data30",
        "Ctrl+Shift+V",
    ),
    TiliaAction.HIERARCHY_DELETE: ActionParams(
        Post.HIERARCHY_DELETE, "Delete hierarchy", "delete30", ""
    ),
    TiliaAction.HIERARCHY_IMPORT_FROM_CSV: ActionParams(
        Post.HIERARCHY_IMPORT_FROM_CSV, "Import from CSV file", "", ""
    ),
    TiliaAction.HARMONY_DELETE: ActionParams(
        Post.HARMONY_DELETE, "Delete harmony", "harmony_delete", ""
    ),
    TiliaAction.HARMONY_ADD: ActionParams(
        Post.HARMONY_ADD, "Add harmony", "harmony_add", "h"
    ),
    TiliaAction.MODE_DELETE: ActionParams(
        Post.MODE_DELETE, "Delete key", "mode_delete", ""
    ),
    TiliaAction.MODE_ADD: ActionParams(Post.MODE_ADD, "Add mode", "mode_add", ""),
    TiliaAction.HARMONY_DISPLAY_AS_ROMAN_NUMERAL: ActionParams(
        Post.HARMONY_DISPLAY_AS_ROMAN_NUMERAL,
        "Display as roman numeral",
        "harmony_display_roman",
        "",
    ),
    TiliaAction.HARMONY_DISPLAY_AS_CHORD_SYMBOL: ActionParams(
        Post.HARMONY_DISPLAY_AS_CHORD_SYMBOL,
        "Display as chord symbol",
        "harmony_display_chord",
        "",
    ),
    TiliaAction.HARMONY_TIMELINE_SHOW_KEYS: ActionParams(
        Post.HARMONY_TIMELINE_SHOW_KEYS, "Show keys", "", ""
    ),
    TiliaAction.HARMONY_TIMELINE_HIDE_KEYS: ActionParams(
        Post.HARMONY_TIMELINE_HIDE_KEYS, "Hide keys", "", ""
    ),
    TiliaAction.FILE_NEW: ActionParams(Post.REQUEST_FILE_NEW, "New...", "", "Ctrl+N"),
    TiliaAction.FILE_OPEN: ActionParams(Post.FILE_OPEN, "Open...", "", "Ctrl+O"),
    TiliaAction.FILE_SAVE: ActionParams(Post.FILE_SAVE, "Save", "", "Ctrl+S"),
    TiliaAction.FILE_SAVE_AS: ActionParams(
        Post.FILE_SAVE_AS, "Save as...", "", "Ctrl+Shift+S"
    ),
    TiliaAction.MEDIA_LOAD_LOCAL: ActionParams(
        Post.UI_MEDIA_LOAD_LOCAL, "Local...", "", "Ctrl+Shift+L"
    ),
    TiliaAction.MEDIA_LOAD_YOUTUBE: ActionParams(
        Post.UI_MEDIA_LOAD_YOUTUBE, "YouTube...", "", ""
    ),
    TiliaAction.METADATA_WINDOW_OPEN: ActionParams(
        Post.WINDOW_METADATA_OPEN, "Edit metadata...", "", ""
    ),
    TiliaAction.SETTINGS_WINDOW_OPEN: ActionParams(
        Post.WINDOW_SETTINGS_OPEN, "Settings...", "", ""
    ),
    TiliaAction.AUTOSAVES_FOLDER_OPEN: ActionParams(
        Post.AUTOSAVES_FOLDER_OPEN, "Autosaves...", "", ""
    ),
    TiliaAction.EDIT_REDO: ActionParams(Post.EDIT_REDO, "Redo", "", "Ctrl+Shift+Z"),
    TiliaAction.EDIT_UNDO: ActionParams(Post.EDIT_UNDO, "Undo", "", "Ctrl+Z"),
    TiliaAction.WINDOW_MANAGE_TIMELINES_OPEN: ActionParams(
        Post.WINDOW_MANAGE_TIMELINES_OPEN, "Manage...", "", ""
    ),
    TiliaAction.TIMELINES_ADD_HIERARCHY_TIMELINE: ActionParams(
        Post.TIMELINE_ADD_HIERARCHY_TIMELINE,
        "Hierarchy",
        "",
        "",
    ),
    TiliaAction.TIMELINES_ADD_MARKER_TIMELINE: ActionParams(
        Post.TIMELINE_ADD_MARKER_TIMELINE,
        "Marker",
        "",
        "",
    ),
    TiliaAction.TIMELINES_ADD_BEAT_TIMELINE: ActionParams(
        Post.TIMELINE_ADD_BEAT_TIMELINE,
        "Beat",
        "",
        "",
    ),
    TiliaAction.TIMELINES_ADD_HARMONY_TIMELINE: ActionParams(
        Post.TIMELINE_ADD_HARMONY_TIMELINE,
        "Harmony",
        "",
        "",
    ),
    TiliaAction.HARMONY_IMPORT_FROM_CSV: ActionParams(
        Post.HARMONY_IMPORT_FROM_CSV, "Import from CSV file", "", ""
    ),
    TiliaAction.TIMELINES_CLEAR: ActionParams(
        Post.TIMELINES_CLEAR, "Clear all", "", ""
    ),
    TiliaAction.TIMELINES_AUTO_SCROLL_ENABLE: ActionParams(
        Post.TIMELINES_AUTO_SCROLL_ENABLE, "Enable auto-scroll", "", ""
    ),
    TiliaAction.TIMELINES_AUTO_SCROLL_DISABLE: ActionParams(
        Post.TIMELINES_AUTO_SCROLL_DISABLE, "Disable auto-scroll", "", ""
    ),
    TiliaAction.TIMELINE_ELEMENT_INSPECT: ActionParams(
        Post.TIMELINE_ELEMENT_INSPECT, "Inspect", "", ""
    ),
    TiliaAction.TIMELINE_ELEMENT_EDIT: ActionParams(
        Post.TIMELINE_ELEMENT_INSPECT, "Edit", "", ""
    ),
    TiliaAction.TIMELINE_ELEMENT_COPY: ActionParams(
        Post.TIMELINE_ELEMENT_COPY, "Copy", "", "Ctrl+C"
    ),
    TiliaAction.TIMELINE_ELEMENT_PASTE: ActionParams(
        Post.TIMELINE_ELEMENT_PASTE, "Paste", "", "Ctrl+V"
    ),
    TiliaAction.TIMELINE_ELEMENT_EXPORT_AUDIO: ActionParams(
        Post.TIMELINE_ELEMENT_EXPORT_AUDIO, "Export to audio", "", ""
    ),
    TiliaAction.TIMELINE_ELEMENT_DELETE: ActionParams(
        Post.TIMELINE_ELEMENT_DELETE, "Delete", "", "Delete"
    ),
    TiliaAction.TIMELINE_NAME_SET: ActionParams(
        Post.TIMELINE_NAME_SET, "Change name", "", ""
    ),
    TiliaAction.TIMELINE_HEIGHT_SET: ActionParams(
        Post.TIMELINE_HEIGHT_SET, "Change height", "", ""
    ),
    TiliaAction.TIMELINE_ORDINAL_INCREASE: ActionParams(
        Post.TIMELINE_ORDINAL_INCREASE_FROM_MANAGE_TIMELINES, "Move timeline up", "", ""
    ),
    TiliaAction.TIMELINE_ORDINAL_DECREASE: ActionParams(
        Post.TIMELINE_ORDINAL_DECREASE_FROM_MANAGE_TIMELINES,
        "Move timeline down",
        "",
        "",
    ),
    TiliaAction.VIEW_ZOOM_IN: ActionParams(Post.VIEW_ZOOM_IN, "Zoom in", "", "Ctrl++"),
    TiliaAction.VIEW_ZOOM_OUT: ActionParams(
        Post.VIEW_ZOOM_OUT, "Zoom out", "", "Ctrl+-"
    ),
    TiliaAction.ABOUT_WINDOW_OPEN: ActionParams(
        Post.WINDOW_ABOUT_OPEN, "About...", "", ""
    ),
    TiliaAction.MEDIA_STOP: ActionParams(Post.PLAYER_STOP, "Stop", "stop15", ""),
    TiliaAction.MEDIA_TOGGLE_PLAY_PAUSE: ActionParams(
        Post.PLAYER_TOGGLE_PLAY_PAUSE, "Play/pause", "playpause", "Space"
    ),
    TiliaAction.INSPECT_WINDOW_CLOSE: ActionParams(
        Post.WINDOW_INSPECT_CLOSE, "Close", "", ""
    ),
    TiliaAction.WEBSITE_HELP_OPEN: ActionParams(
        Post.WEBSITE_HELP_OPEN, "Help...", "", ""
    ),
}

_taction_to_qaction: dict[TiliaAction, QAction] = {}  # will be populated on startup


def get_qaction(tilia_action: TiliaAction):
    return _taction_to_qaction[tilia_action]


def trigger(tilia_action: TiliaAction):
    _taction_to_qaction[tilia_action].trigger()
