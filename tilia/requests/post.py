import logging
import os
from enum import Enum, auto
from typing import Callable, Any

from tilia import settings

logger = logging.getLogger(__name__)


class Post(Enum):
    TIMELINE_ELEMENT_PASTE_COMPLETE = auto()
    HARMONY_IMPORT_FROM_CSV = auto()
    MODE_DISPLAY_AS_ROMAN_NUMERAL = auto()
    MODE_ADD = auto()
    MODE_DELETE = auto()
    HARMONY_TIMELINE_HIDE_KEYS = auto()
    HARMONY_TIMELINE_SHOW_KEYS = auto()
    HARMONY_DISPLAY_AS_ROMAN_NUMERAL = auto()
    HARMONY_DISPLAY_AS_CHORD_SYMBOL = auto()
    TIMELINE_ADD_HARMONY_TIMELINE = auto()
    HARMONY_DELETE = auto()
    HARMONY_ADD = auto()
    TIMELINE_ADD_HIERARCHY_TIMELINE = auto()
    TIMELINE_ADD_MARKER_TIMELINE = auto()
    TIMELINE_ADD_BEAT_TIMELINE = auto()
    PLAYER_AVAILABLE = auto()
    APP_CLEAR = auto()
    APP_CLOSE = auto()
    APP_FILE_LOAD = auto()
    APP_MEDIA_LOAD = auto()
    APP_RECORD_STATE = auto()
    APP_SETUP_BLANK_FILE = auto()
    PLAYER_ENABLE_CONTROLS = auto()
    PLAYER_DISABLE_CONTROLS = auto()
    UI_MEDIA_LOAD_YOUTUBE = auto()
    PLAYER_DURATION_CHANGED = auto()
    HIERARCHY_SELECTED = auto()
    HIERARCHY_DESELECTED = auto()
    TIMELINE_VIEW_DOUBLE_LEFT_CLICK = auto()
    TIMELINES_CROP_DONE = auto()
    UI_MEDIA_LOAD_LOCAL = auto()
    APP_STATE_RESTORE = auto()
    BEAT_ADD = auto()
    BEAT_DELETE = auto()
    BEAT_DISTRIBUTE = auto()
    BEAT_IMPORT_FROM_CSV = auto()
    BEAT_RESET_MEASURE_NUMBER = auto()
    BEAT_SET_AMOUNT_IN_MEASURE = auto()
    BEAT_SET_MEASURE_NUMBER = auto()
    BEAT_TIME_CHANGED = auto()
    CANVAS_RIGHT_CLICK = auto()
    DISPLAY_ERROR = auto()
    EDIT_REDO = auto()
    EDIT_UNDO = auto()
    ELEMENT_DRAG_END = auto()
    ELEMENT_DRAG_START = auto()
    EXPLORER_AUDIO_INFO_FROM_SEARCH_RESULT = auto()
    EXPLORER_DISPLAY_SEARCH_RESULTS = auto()
    EXPLORER_LOAD_MEDIA = auto()
    EXPLORER_PLAY = auto()
    EXPLORER_SEARCH = auto()
    FILE_OPEN = auto()
    FILE_SAVE = auto()
    FILE_SAVE_AS = auto()
    FOCUS_TIMELINES = auto()
    HIERARCHY_ADD_POST_END = auto()
    HIERARCHY_ADD_PRE_START = auto()
    HIERARCHY_COLOR_SET = auto()
    HIERARCHY_COLOR_RESET = auto()
    HIERARCHY_CREATE_CHILD = auto()
    HIERARCHY_DECREASE_LEVEL = auto()
    HIERARCHY_DELETE = auto()
    HIERARCHY_GENEALOGY_CHANGED = auto()
    HIERARCHY_GROUP = auto()
    HIERARCHY_IMPORT_FROM_CSV = auto()
    HIERARCHY_INCREASE_LEVEL = auto()
    HIERARCHY_LEVEL_CHANGED = auto()
    HIERARCHY_MERGE = auto()
    HIERARCHY_PASTE = auto()
    HIERARCHY_POSITION_CHANGED = auto()
    HIERARCHY_SPLIT = auto()
    INSPECTABLE_ELEMENT_DESELECTED = auto()
    INSPECTABLE_ELEMENT_SELECTED = auto()
    INSPECTOR_FIELD_EDITED = auto()
    KEY_PRESS_DELETE = auto()
    KEY_PRESS_DOWN = auto()
    KEY_PRESS_ENTER = auto()
    KEY_PRESS_LEFT = auto()
    KEY_PRESS_RIGHT = auto()
    KEY_PRESS_UP = auto()
    LEFT_BUTTON_CLICK = auto()
    MARKER_ADD = auto()
    MARKER_DELETE = auto()
    MARKER_IMPORT_FROM_CSV = auto()
    MEDIA_METADATA_FIELD_SET = auto()
    MERGE_RANGE_BUTTON = auto()
    METADATA_ADD_FIELD = auto()
    METADATA_REMOVE_FIELD = auto()
    PLAYBACK_AREA_SET_WIDTH = auto()
    PLAYER_CHANGE_TO_AUDIO_PLAYER = auto()
    PLAYER_CHANGE_TO_VIDEO_PLAYER = auto()
    PLAYER_EXPORT_AUDIO = auto()
    PLAYER_URL_CHANGED = auto()
    PLAYER_CURRENT_TIME_CHANGED = auto()
    PLAYER_MEDIA_UNLOADED = auto()
    PLAYER_PAUSED = auto()
    PLAYER_REQUEST_TO_LOAD_MEDIA = auto()
    PLAYER_SEEK = auto()
    PLAYER_SEEK_IF_NOT_PLAYING = auto()
    PLAYER_REQUEST_TO_UNLOAD_MEDIA = auto()
    PLAYER_STOP = auto()
    PLAYER_STOPPED = auto()
    PLAYER_STOPPING = auto()
    PLAYER_TOGGLE_PLAY_PAUSE = auto()
    PLAYER_UNPAUSED = auto()
    REQUEST_CHANGE_TIMELINE_WIDTH = auto()
    REQUEST_CLEAR_ALL_TIMELINES = auto()
    REQUEST_CLEAR_TIMELINE = auto()
    REQUEST_CLEAR_UI = auto()
    REQUEST_DELETE_TIMELINE = auto()
    REQUEST_FILE_NEW = auto()
    REQUEST_FILE_OPEN_PATH = auto()
    REQUEST_IMPORT_MEDIA_METADATA_FROM_PATH = auto()
    REQUEST_SAVE_TO_PATH = auto()
    SELECTION_BOX_DESELECT_ITEM = auto()
    SELECTION_BOX_SELECT_ITEM = auto()
    SLIDER_DRAG_END = auto()
    SLIDER_DRAG_START = auto()
    TIMELINES_AUTO_SCROLL_DISABLE = auto()
    TIMELINES_AUTO_SCROLL_ENABLE = auto()
    TIMELINES_CLEAR = auto()
    TIMELINE_ADD = auto()
    TIMELINE_CLEAR_FROM_MANAGE_TIMELINES = auto()
    TIMELINE_COLLECTION_STATE_RESTORED = auto()
    TIMELINE_COMPONENT_CREATED = auto()
    TIMELINE_COMPONENT_DELETED = auto()
    TIMELINE_COMPONENT_DELETE_DONE = auto()
    TIMELINE_COMPONENT_DESELECTED = auto()
    TIMELINE_COMPONENT_SELECTED = auto()
    TIMELINE_COMPONENT_SET_DATA_DONE = auto()
    TIMELINE_COMPONENT_SET_DATA_FAILED = auto()
    TIMELINE_CREATE_DONE = auto()
    TIMELINE_DELETE = auto()
    TIMELINE_DELETE_DONE = auto()
    TIMELINE_DELETE_FROM_MANAGE_TIMELINES = auto()
    TIMELINE_ELEMENT_COLOR_RESET = auto()
    TIMELINE_ELEMENT_COLOR_SET = auto()
    TIMELINE_ELEMENT_COPY = auto()
    TIMELINE_ELEMENT_COPY_DONE = auto()
    TIMELINE_ELEMENT_DELETE = auto()
    TIMELINE_ELEMENT_EXPORT_AUDIO = auto()
    TIMELINE_ELEMENT_INSPECT = auto()
    TIMELINE_ELEMENT_PASTE = auto()
    TIMELINE_ELEMENT_PASTE_ALL = auto()
    TIMELINE_HEIGHT_SET = auto()
    TIMELINE_HEIGHT_SET_DONE = auto()
    TIMELINE_IS_VISIBLE_SET_FROM_MANAGE_TIMELINES = auto()
    TIMELINE_KEY_PRESS_DOWN = auto()
    TIMELINE_KEY_PRESS_LEFT = auto()
    TIMELINE_KEY_PRESS_RIGHT = auto()
    TIMELINE_KEY_PRESS_UP = auto()
    TIMELINE_KIND_INSTANCED = auto()
    TIMELINE_KIND_NOT_INSTANCED = auto()
    TIMELINE_NAME_SET = auto()
    TIMELINE_ORDINAL_DECREASE_FROM_MANAGE_TIMELINES = auto()
    TIMELINE_ORDINAL_INCREASE_FROM_MANAGE_TIMELINES = auto()
    TIMELINE_ORDINAL_SET = auto()
    TIMELINE_PREPARING_TO_DRAG = auto()
    TIMELINE_SET_DATA_DONE = auto()
    TIMELINE_VIEW_LEFT_BUTTON_DRAG = auto()
    TIMELINE_VIEW_LEFT_BUTTON_RELEASE = auto()
    TIMELINE_VIEW_LEFT_CLICK = auto()
    TIMELINE_VIEW_RIGHT_CLICK = auto()
    TIMELINE_WIDTH_SET_DONE = auto()
    UI_CLOSE = auto()
    UI_MEDIA_LOAD = auto()
    UNDO_MANAGER_SET_IS_RECORDING = auto()
    VIEW_ZOOM_IN = auto()
    VIEW_ZOOM_OUT = auto()
    WINDOW_ABOUT_CLOSED = auto()
    WINDOW_ABOUT_OPEN = auto()
    WINDOW_INSPECT_CLOSED = auto()
    WINDOW_INSPECT_OPENED = auto()
    WINDOW_MANAGE_TIMELINES_CLOSE_DONE = auto()
    WINDOW_MANAGE_TIMELINES_OPEN = auto()
    WINDOW_METADATA_CLOSED = auto()
    WINDOW_METADATA_OPEN = auto()
    WINDOW_METADATA_OPENED = auto()
    WINDOW_SETTINGS_OPEN = auto()


posts_to_listeners: dict[Post, Any] = {post: {} for post in Post}
listeners_to_posts: dict[Any, list[Post]] = {}


def _get_posts_excluded_from_log() -> [Post]:
    result = []
    for name in os.environ.get("EXCLUDE_FROM_LOG", "").split(";"):
        result.append(Post[name])
    return result


def _log_post(post, *args, **kwargs):
    print(
        f"{post.name:<40} {str((args, kwargs)):<100} {list(posts_to_listeners[post])}"
    )


def post(post: Post, *args, **kwargs) -> None:
    if os.environ.get("LOG_REQUESTS", 0) and post not in _get_posts_excluded_from_log():
        _log_post(post, args, kwargs)
    for listener, callback in posts_to_listeners[post].copy().items():
        callback(*args, **kwargs)


def listen(listener: Any, post: Post, callback: Callable) -> None:
    posts_to_listeners[post][listener] = callback

    if listener not in listeners_to_posts.keys():
        listeners_to_posts[listener] = [post]
    else:
        listeners_to_posts[listener].append(post)


def listen_to_multiple(
    listener: Any, posts_and_callbacks: list[tuple[Post, Callable]]
) -> None:
    for post, callback in posts_and_callbacks:
        listen(listener, post, callback)


def stop_listening(listener: Any, post: Post) -> None:
    try:
        posts_to_listeners[post].pop(listener)
    except KeyError:
        logger.debug(f"Can't unsubscribe. '{listener} is a listener of {post}'")
        return

    listeners_to_posts[listener].remove(post)

    if not listeners_to_posts[listener]:
        listeners_to_posts.pop(listener)


def stop_listening_to_all(listener: Any) -> None:
    if listener not in listeners_to_posts.keys():
        return

    for post in listeners_to_posts[listener].copy():
        stop_listening(listener, post)
