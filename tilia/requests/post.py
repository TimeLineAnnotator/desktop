import logging
from enum import Enum, auto
from typing import Callable, Any

from tilia import settings

logger = logging.getLogger(__name__)


class Post(Enum):
    TIMELINE_ORDER_SWAPPED = auto()
    ABOUT_WINDOW_CLOSED = auto()
    ADD_RANGE_BUTTON = auto()
    BEAT_TIME_CHANGED = auto()
    BEAT_TOOLBAR_BUTTON_ADD = auto()
    BEAT_TOOLBAR_BUTTON_DELETE = auto()
    BEAT_UPDATED = auto()
    CANVAS_LEFT_CLICK = auto()
    CANVAS_RIGHT_CLICK = auto()
    COMPONENT_CREATE_REQUEST = auto()
    CREATE_RANGE_FROM_BUTTON = auto()
    DEBUG_SELECTED_ELEMENTS = auto()
    DELETE_RANGE_BUTTON = auto()
    DESELECTED_OBJECT = auto()
    ELEMENT_DRAG_END = auto()
    ELEMENT_DRAG_START = auto()
    EXPLORER_AUDIO_INFO_FROM_SEARCH_RESULT = auto()
    EXPLORER_DISPLAY_SEARCH_RESULTS = auto()
    EXPLORER_LOAD_MEDIA = auto()
    EXPLORER_PLAY = auto()
    EXPLORER_SEARCH = auto()
    FOCUS_TIMELINES = auto()
    FREEZE_LABELS_SET = auto()
    HIERARCHIES_DESERIALIZED = auto()
    HIERARCHY_GENEALOGY_CHANGED = auto()
    HIERARCHY_LEVEL_CHANGED = auto()
    HIERARCHY_POSITION_CHANGED = auto()
    HIERARCHY_TIMELINE_UI_CREATED_INITIAL_HIERARCHY = auto()
    HIERARCHY_TOOLBAR_CREATE_CHILD = auto()
    HIERARCHY_TOOLBAR_DELETE = auto()
    HIERARCHY_TOOLBAR_GROUP = auto()
    HIERARCHY_TOOLBAR_LEVEL_DECREASE = auto()
    HIERARCHY_TOOLBAR_LEVEL_INCREASE = auto()
    HIERARCHY_TOOLBAR_MERGE = auto()
    HIERARCHY_TOOLBAR_PASTE = auto()
    HIERARCHY_TOOLBAR_PASTE_WITH_CHILDREN = auto()
    HIERARCHY_TOOLBAR_SPLIT = auto()
    INSPECTABLE_ELEMENT_DESELECTED = auto()
    INSPECTABLE_ELEMENT_SELECTED = auto()
    INSPECTOR_FIELD_EDITED = auto()
    INSPECTOR_WINDOW_OPENED = auto()
    INSPECT_WINDOW_CLOSED = auto()
    JOIN_RANGE_BUTTON = auto()
    KEY_PRESS_CONTROL_C = auto()
    KEY_PRESS_CONTROL_SHIFT_V = auto()
    KEY_PRESS_CONTROL_V = auto()
    KEY_PRESS_DELETE = auto()
    KEY_PRESS_DOWN = auto()
    KEY_PRESS_ENTER = auto()
    KEY_PRESS_LEFT = auto()
    KEY_PRESS_RIGHT = auto()
    KEY_PRESS_UP = auto()
    LEFT_BUTTON_CLICK = auto()
    MANAGE_TIMELINES_WINDOW_CLOSED = auto()
    MARKER_TOOLBAR_BUTTON_ADD = auto()
    MARKER_TOOLBAR_BUTTON_DELETE = auto()
    MENU_OPTION_FILE_LOAD_MEDIA = auto()
    MERGE_RANGE_BUTTON = auto()
    METADATA_WINDOW_CLOSED = auto()
    METADATA_WINDOW_OPENED = auto()
    PLAYER_CHANGE_TO_AUDIO_PLAYER = auto()
    PLAYER_CHANGE_TO_VIDEO_PLAYER = auto()
    PLAYER_MEDIA_LOADED = auto()
    PLAYER_MEDIA_TIME_CHANGE = auto()
    PLAYER_MEDIA_UNLOADED = auto()
    PLAYER_PAUSED = auto()
    PLAYER_REQUEST_TO_LOAD_MEDIA = auto()
    PLAYER_REQUEST_TO_PLAYPAUSE = auto()
    PLAYER_REQUEST_TO_SEEK = auto()
    PLAYER_REQUEST_TO_SEEK_IF_NOT_PLAYING = auto()
    PLAYER_REQUEST_TO_STOP = auto()
    PLAYER_REQUEST_TO_UNLOAD_MEDIA = auto()
    PLAYER_STOPPED = auto()
    PLAYER_STOPPING = auto()
    PLAYER_UNPAUSED = auto()
    REQUEST_ADD_MEDIA_METADATA_FIELD = auto()
    REQUEST_AUTO_SAVE_START = auto()
    REQUEST_CHANGE_TIMELINE_WIDTH = auto()
    REQUEST_CLEAR_ALL_TIMELINES = auto()
    REQUEST_CLEAR_APP = auto()
    REQUEST_CLEAR_TIMELINE = auto()
    REQUEST_CLEAR_UI = auto()
    REQUEST_CLOSE_APP = auto()
    REQUEST_DELETE_COMPONENT = auto()
    REQUEST_DELETE_TIMELINE = auto()
    REQUEST_DISPLAY_ERROR = auto()
    REQUEST_EXPORT_AUDIO = auto()
    REQUEST_FILE_NEW = auto()
    REQUEST_FILE_OPEN = auto()
    REQUEST_FILE_OPEN_PATH = auto()
    REQUEST_FOCUS_TIMELINES = auto()
    REQUEST_IMPORT_CSV_HIERARCHIES = auto()
    REQUEST_IMPORT_CSV_MARKERS = auto()
    REQUEST_LOAD_FILE = auto()
    REQUEST_LOAD_MEDIA = auto()
    REQUEST_MERGE = auto()
    REQUEST_OPEN_SETTINGS = auto()
    REQUEST_RECORD_STATE = auto()
    REQUEST_REMOVE_MEDIA_METADATA_FIELD = auto()
    REQUEST_RESTORE_APP_STATE = auto()
    REQUEST_SAVE = auto()
    REQUEST_SAVE_AS = auto()
    REQUEST_SETUP_BLANK_FILE = auto()
    REQUEST_TIMELINE_CLEAR = auto()
    REQUEST_TIMELINE_CLEAR_ALL = auto()
    REQUEST_TIMELINE_CREATE = auto()
    REQUEST_TIMELINE_DELETE = auto()
    REQUEST_TO_REDO = auto()
    REQUEST_TO_UNDO = auto()
    REQUEST_ZOOM_IN = auto()
    REQUEST_ZOOM_OUT = auto()
    RIGHT_CLICK_MENU_NEW = auto()
    RIGHT_CLICK_MENU_OPTION_CLICK = auto()
    ROOT_WINDOW_RESIZED = auto()
    SEEK_TO_OBJECT_BFR = auto()
    SELECTED_OBJECT = auto()
    SELECTION_BOX_REQUEST_DESELECT = auto()
    SELECTION_BOX_REQUEST_SELECT = auto()
    REQUEST_SET_MEDIA_METADATA_FIELD = auto()
    SLIDER_DRAG_END = auto()
    SLIDER_DRAG_START = auto()
    SPLIT_RANGE_BUTTON = auto()
    REQUEST_MOVE_TIMELINE_DOWN_IN_ORDER = auto()
    REQUEST_MOVE_TIMELINE_UP_IN_ORDER = auto()
    TIMELINES_REQUEST_TO_HIDE_TIMELINE = auto()
    TIMELINES_REQUEST_TO_SHOW_TIMELINE = auto()
    TIMELINE_COLLECTION_STATE_RESTORED = auto()
    TIMELINE_COMPONENT_COPIED = auto()
    TIMELINE_COMPONENT_CREATED = auto()
    TIMELINE_COMPONENT_DELETED = auto()
    TIMELINE_COMPONENT_DESELECTED = auto()
    TIMELINE_COMPONENT_SELECTED = auto()
    TIMELINE_CREATED = auto()
    TIMELINE_DELETED = auto()
    TIMELINE_HEIGHT_CHANGED = auto()
    TIMELINE_KIND_INSTANCED = auto()
    TIMELINE_KIND_UNINSTANCED = auto()
    TIMELINE_LEFT_BUTTON_DRAG = auto()
    TIMELINE_LEFT_BUTTON_RELEASE = auto()
    TIMELINE_LEFT_CLICK = auto()
    TIMELINE_LEFT_RELEASED = auto()
    TIMELINE_MOUSE_DRAG = auto()
    TIMELINE_NAME_CHANGED = auto()
    TIMELINE_PREPARING_TO_DRAG = auto()
    TIMELINE_WIDTH_CHANGED = auto()
    TIMELINE_WIDTH_CHANGE_REQUEST = auto()
    UI_REQUEST_WINDOW_ABOUT = auto()
    UI_REQUEST_WINDOW_DEVELOPMENT = auto()
    UI_REQUEST_WINDOW_INSPECTOR = auto()
    UI_REQUEST_WINDOW_MANAGE_TIMELINES = auto()
    UI_REQUEST_WINDOW_METADATA = auto()


posts_to_listeners: dict[Post, Any] = {}
listeners_to_posts: dict[Any, list[Post]] = {}

for post in Post:
    posts_to_listeners[post] = {}

log_posts = settings.get("dev", "log_requests")


def post(post: Post, *args, logging_level=10, **kwargs) -> None:
    if log_posts:
        logger.log(
            logging_level, f"Posting post {post.name} with {args=} and {kwargs=}."
        )

    for listener, callback in posts_to_listeners[post].copy().items():
        if log_posts:
            logger.log(logging_level, f"    Notifying {listener}...")
        try:
            callback(*args, **kwargs)
        except Exception as exc:
            raise Exception(
                f"Exception when notifying about {post} with {args=}, {kwargs=}"
            ) from exc

    if log_posts:
        logger.log(logging_level, f"Notified about post '{post}'.")


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
