from typing import Any

from tilia.dirs import IMG_DIR
from tilia.requests.post import post, Post

from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtGui import QAction, QKeySequence, QIcon

from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.windows import WindowKind


def get_img_path(basename: str):
    return IMG_DIR / f"{basename}.png"


def _get_request_callback(request: Post, args: tuple[Any], kwargs: dict[str, Any]):
    if args or kwargs:

        def callback():
            return post(request, *args, **kwargs)

    else:

        def callback():
            return post(request)

    return callback


def register_action(
    parent, name, request, text, shortcut, icon, args=None, kwargs=None, callback=None
):
    action = QAction(parent)

    action.setText(text)
    action.setToolTip(f"{text} ({shortcut})" if shortcut else text)

    if shortcut:
        action.setShortcut(QKeySequence(shortcut))

    if icon:
        action.setIcon(QIcon(str(get_img_path(icon))))
    action.setIconVisibleInMenu(False)

    args = args or []
    kwargs = kwargs or {}
    if not callback:
        callback = _get_request_callback(request, args, kwargs)

    action.triggered.connect(callback)

    _name_to_callback[name] = callback
    _name_to_action[name] = action


def get_qaction(name):
    try:
        return _name_to_action[name]
    except KeyError:
        raise ValueError(f"Unknown action: {name}")


def setup_actions(parent: QMainWindow):
    for action_params in default_actions:
        register_action(parent, *action_params)


def execute(name: str):
    return _name_to_callback[name]()


_name_to_action = {}
_name_to_callback = {}

default_actions = [
    ("app_close", Post.APP_CLOSE, "Close tilia", "", "Close"),
    ("beat_add", Post.BEAT_ADD, "Add beat at current position", "b", "beat_add"),
    ("beat_distribute", Post.BEAT_DISTRIBUTE, "Distribute", "", "beat_distribute"),
    (
        "beat_set_measure_number",
        Post.BEAT_SET_MEASURE_NUMBER,
        "Set measure number",
        "",
        "beat_set_number",
    ),
    (
        "beat_reset_measure_number",
        Post.BEAT_RESET_MEASURE_NUMBER,
        "Reset measure number",
        "",
        "beat_reset_number",
    ),
    (
        "beat_set_amount_in_measure",
        Post.BEAT_SET_AMOUNT_IN_MEASURE,
        "Set beat amount in measure",
        "",
        "",
    ),
    ("beat_timeline_fill", Post.BEAT_TIMELINE_FILL, "Fill timeline with beats", "", ""),
    (
        "marker_add",
        Post.MARKER_ADD,
        "Add marker at current position",
        "m",
        "add_marker30",
    ),
    (
        "timeline_element_color_set",
        Post.TIMELINE_ELEMENT_COLOR_SET,
        "Change color",
        "",
        "",
    ),
    (
        "timeline_element_color_reset",
        Post.TIMELINE_ELEMENT_COLOR_RESET,
        "Reset color",
        "",
        "",
    ),
    (
        "hierarchy_split",
        Post.HIERARCHY_SPLIT,
        "Split at current position",
        "s",
        "split30",
    ),
    ("hierarchy_merge", Post.HIERARCHY_MERGE, "Merge", "e", "merge30"),
    ("hierarchy_group", Post.HIERARCHY_GROUP, "Group", "g", "group30"),
    (
        "hierarchy_increase_level",
        Post.HIERARCHY_INCREASE_LEVEL,
        "Move up a level",
        "Ctrl+Up",
        "lvlup30",
    ),
    (
        "hierarchy_decrease_level",
        Post.HIERARCHY_DECREASE_LEVEL,
        "Move down a level",
        "Ctrl+Down",
        "lvldwn30",
    ),
    (
        "hierarchy_create_child",
        Post.HIERARCHY_CREATE_CHILD,
        "Create child",
        "",
        "below30",
    ),
    ("hierarchy_add_pre_start", Post.HIERARCHY_ADD_PRE_START, "Add pre-start", "", ""),
    ("hierarchy_add_post_end", Post.HIERARCHY_ADD_POST_END, "Add post-end", "", ""),
    (
        "timeline_element_paste_complete",
        Post.TIMELINE_ELEMENT_PASTE_COMPLETE,
        "Pas&te complete",
        "Ctrl+Shift+V",
        "paste_with_data30",
    ),
    ("harmony_add", Post.HARMONY_ADD, "Add harmony", "h", "harmony_add"),
    ("mode_add", Post.MODE_ADD, "Add mode", "", "mode_add"),
    (
        "harmony_display_as_roman_numeral",
        Post.HARMONY_DISPLAY_AS_ROMAN_NUMERAL,
        "Display as roman numeral",
        "",
        "harmony_display_roman",
    ),
    (
        "harmony_display_as_chord_symbol",
        Post.HARMONY_DISPLAY_AS_CHORD_SYMBOL,
        "Display as chord symbol",
        "",
        "harmony_display_chord",
    ),
    (
        "harmony_timeline_show_keys",
        Post.HARMONY_TIMELINE_SHOW_KEYS,
        "Show keys",
        "",
        "",
    ),
    (
        "harmony_timeline_hide_keys",
        Post.HARMONY_TIMELINE_HIDE_KEYS,
        "Hide keys",
        "",
        "",
    ),
    ("file_new", Post.REQUEST_FILE_NEW, "&New...", "Ctrl+N", ""),
    ("file_open", Post.FILE_OPEN, "&Open...", "Ctrl+O", ""),
    ("file_save", Post.FILE_SAVE, "&Save", "Ctrl+S", ""),
    ("file_save_as", Post.FILE_SAVE_AS, "Save &As...", "Ctrl+Shift+S", ""),
    ("file_export_json", Post.FILE_EXPORT, "&JSON", "", ""),
    ("file_export_img", Post.FILE_EXPORT, "&Image", "", ""),
    ("media_load_local", Post.UI_MEDIA_LOAD_LOCAL, "&Local...", "Ctrl+Shift+L", ""),
    ("media_load_youtube", Post.UI_MEDIA_LOAD_YOUTUBE, "&YouTube...", "", ""),
    ("metadata_window_open", Post.WINDOW_OPEN, "Edit &Metadata...", "", ""),
    ("settings_window_open", Post.WINDOW_OPEN, "&Settings...", "", ""),
    (
        "autosaves_folder_open",
        Post.AUTOSAVES_FOLDER_OPEN,
        "Open autosa&ves folder...",
        "",
        "",
    ),
    ("edit_redo", Post.EDIT_REDO, "&Redo", "Ctrl+Shift+Z", ""),
    ("edit_undo", Post.EDIT_UNDO, "&Undo", "Ctrl+Z", ""),
    ("window_manage_timelines_open", Post.WINDOW_OPEN, "&Manage...", "", ""),
    ("timelines_clear", Post.TIMELINES_CLEAR, "Clear all", "", ""),
    ("timeline_element_inspect", Post.TIMELINE_ELEMENT_INSPECT, "Inspect", "", ""),
    ("timeline_element_edit", Post.TIMELINE_ELEMENT_INSPECT, "&Edit", "", ""),
    ("timeline_element_copy", Post.TIMELINE_ELEMENT_COPY, "&Copy", "Ctrl+C", ""),
    ("timeline_element_paste", Post.TIMELINE_ELEMENT_PASTE, "&Paste", "Ctrl+V", ""),
    (
        "timeline_element_export_audio",
        Post.TIMELINE_ELEMENT_EXPORT_AUDIO,
        "Export to audio",
        "",
        "",
    ),
    ("timeline_element_delete", Post.TIMELINE_ELEMENT_DELETE, "Delete", "Delete", ""),
    ("timeline_name_set", Post.TIMELINE_NAME_SET, "Change name", "", ""),
    ("timeline_height_set", Post.TIMELINE_HEIGHT_SET, "Change height", "", ""),
    ("view_zoom_in", Post.VIEW_ZOOM_IN, "Zoom &In", "Ctrl++", ""),
    ("view_zoom_out", Post.VIEW_ZOOM_OUT, "Zoom &Out", "Ctrl+-", ""),
    ("about_window_open", Post.WINDOW_OPEN, "&About...", "", ""),
    ("media_stop", Post.PLAYER_STOP, "Stop", "", "stop15"),
    ("website_help_open", Post.WEBSITE_HELP_OPEN, "&Help...", "", ""),
    ("pdf_marker_add", Post.PDF_MARKER_ADD, "Add PDF marker", "p", "pdf_add"),
    ("import_csv_harmony_timeline", Post.IMPORT_CSV, "&Import from CSV file", "", ""),
    ("import_csv_pdf_timeline", Post.IMPORT_CSV, "&Import from CSV file", "", ""),
    ("import_csv_hierarchy_timeline", Post.IMPORT_CSV, "&Import from CSV file", "", ""),
    ("import_csv_marker_timeline", Post.IMPORT_CSV, "&Import from CSV file", "", ""),
    ("import_csv_beat_timeline", Post.IMPORT_CSV, "&Import from CSV file", "", ""),
    ("import_musicxml", Post.IMPORT_MUSICXML, "&Import from musicxml file", "", ""),
    ("score_annotation_add", None, "Add Annotation (Return)", "", "annotation_add"),
    (
        "score_annotation_delete",
        None,
        "Delete Annotation (Delete)",
        "",
        "annotation_delete",
    ),
    (
        "score_annotation_edit",
        None,
        "Edit Annotation",
        "Shift+Return",
        "annotation_edit",
    ),
    (
        "score_annotation_font_dec",
        None,
        "Decrease Annotation Font",
        "Shift+Down",
        "annotation_font_dec",
    ),
    (
        "score_annotation_font_inc",
        None,
        "Increase Annotation Font",
        "Shift+Up",
        "annotation_font_inc",
    ),
    ("file_export_json", Post.FILE_EXPORT, "&JSON", "", "", (None, "json")),
    ("file_export_img", Post.FILE_EXPORT, "&Image", "", "", (None, "img")),
    (
        "metadata_window_open",
        Post.WINDOW_OPEN,
        "Edit &Metadata...",
        "",
        "",
        (WindowKind.MEDIA_METADATA,),
    ),
    (
        "settings_window_open",
        Post.WINDOW_OPEN,
        "&Settings...",
        "",
        "",
        (WindowKind.SETTINGS,),
    ),
    (
        "window_manage_timelines_open",
        Post.WINDOW_OPEN,
        "&Manage...",
        "",
        "",
        (WindowKind.MANAGE_TIMELINES,),
    ),
    ("about_window_open", Post.WINDOW_OPEN, "&About...", "", "", (WindowKind.ABOUT,)),
    (
        "import_csv_harmony_timeline",
        Post.IMPORT_CSV,
        "&Import from CSV file",
        "",
        "",
        (TimelineKind.HARMONY_TIMELINE,),
    ),
    (
        "import_csv_pdf_timeline",
        Post.IMPORT_CSV,
        "&Import from CSV file",
        "",
        "",
        (TimelineKind.PDF_TIMELINE,),
    ),
    (
        "import_csv_hierarchy_timeline",
        Post.IMPORT_CSV,
        "&Import from CSV file",
        "",
        "",
        (TimelineKind.HIERARCHY_TIMELINE,),
    ),
    (
        "import_csv_marker_timeline",
        Post.IMPORT_CSV,
        "&Import from CSV file",
        "",
        "",
        (TimelineKind.MARKER_TIMELINE,),
    ),
    (
        "import_csv_beat_timeline",
        Post.IMPORT_CSV,
        "&Import from CSV file",
        "",
        "",
        (TimelineKind.BEAT_TIMELINE,),
    ),
]
