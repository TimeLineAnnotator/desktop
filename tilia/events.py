import logging
from enum import Enum, auto
from typing import Callable, Any

from tilia import settings

logger = logging.getLogger(__name__)


class Event(Enum):
    ABOUT_WINDOW_CLOSED = auto()
    ADD_RANGE_BUTTON = auto()
    BEAT_TOOLBAR_BUTTON_ADD = auto()
    BEAT_TOOLBAR_BUTTON_DELETE = auto()
    CANVAS_LEFT_CLICK = auto()
    CANVAS_RIGHT_CLICK = auto()
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
    FILE_REQUEST_TO_OPEN = auto()
    FILE_REQUEST_TO_SAVE = auto()
    FOCUS_TIMELINES = auto()
    FREEZE_LABELS_SET = auto()
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
    METADATA_FIELD_EDITED = auto()
    METADATA_NEW_FIELDS = auto()
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
    REQUEST_ADD_TIMELINE = auto()
    REQUEST_AUTO_SAVE_START = auto()
    REQUEST_CHANGE_TIMELINE_WIDTH = auto()
    REQUEST_CLEAR_ALL_TIMELINES = auto()
    REQUEST_CLEAR_TIMELINE = auto()
    REQUEST_CLOSE_APP = auto()
    REQUEST_DELETE_COMPONENT = auto()
    REQUEST_DELETE_TIMELINE = auto()
    REQUEST_DISPLAY_ERROR = auto()
    REQUEST_EXPORT_AUDIO_SEGMENT = auto()
    REQUEST_FOCUS_TIMELINES = auto()
    REQUEST_IMPORT_CSV_HIERARCHIES = auto()
    REQUEST_IMPORT_CSV_MARKERS = auto()
    REQUEST_LOAD_MEDIA = auto()
    REQUEST_MERGE = auto()
    REQUEST_NEW_FILE = auto()
    REQUEST_OPEN_SETTINGS = auto()
    REQUEST_RECORD_STATE = auto()
    REQUEST_RESTORE_APP_STATE = auto()
    REQUEST_TIMELINES__LOAD_TIMELINE = auto()
    REQUEST_TIMELINE_FRONTEND__RESET_TIMELINE_SIZE = auto()
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
    SLIDER_DRAG_END = auto()
    SLIDER_DRAG_START = auto()
    SPLIT_RANGE_BUTTON = auto()
    TILIA_FILE_LOADED = auto()
    TIMELINES_REQUEST_MOVE_DOWN_IN_DISPLAY_ORDER = auto()
    TIMELINES_REQUEST_MOVE_UP_IN_DISPLAY_ORDER = auto()
    TIMELINES_REQUEST_TO_HIDE_TIMELINE = auto()
    TIMELINES_REQUEST_TO_SHOW_TIMELINE = auto()
    TIMELINE_COMPONENT_COPIED = auto()
    TIMELINE_COMPONENT_DESELECTED = auto()
    TIMELINE_COMPONENT_SELECTED = auto()
    TIMELINE_KIND_INSTANCED = auto()
    TIMELINE_KIND_UNINSTANCED = auto()
    TIMELINE_LEFT_BUTTON_DRAG = auto()
    TIMELINE_LEFT_BUTTON_RELEASE = auto()
    TIMELINE_LEFT_CLICK = auto()
    TIMELINE_LEFT_RELEASED = auto()
    TIMELINE_MOUSE_DRAG = auto()
    TIMELINE_PREPARING_TO_DRAG = auto()
    UI_REQUEST_WINDOW_ABOUT = auto()
    UI_REQUEST_WINDOW_DEVELOPMENT = auto()
    UI_REQUEST_WINDOW_INSPECTOR = auto()
    UI_REQUEST_WINDOW_MANAGE_TIMELINES = auto()
    UI_REQUEST_WINDOW_METADATA = auto()


events_to_subscribers: dict[Event, Any] = {}
subscribers_to_events: dict[Any, list[Event]] = {}

for event in Event:
    events_to_subscribers[event] = {}

log_events = settings.get("dev", "log_events")


def post(event: Event, *args, logging_level=10, **kwargs) -> None:
    if log_events:
        logger.log(
            logging_level, f"Posting event {event.name} with {args=} and {kwargs=}."
        )

    for subscriber, callback in events_to_subscribers[event].copy().items():
        if log_events:
            logger.log(logging_level, f"    Notifying {subscriber}...")
        try:
            callback(*args, **kwargs)
        except Exception as exc:
            raise Exception(
                f"Exception when notifying about {event} with {args=}, {kwargs=}"
            ) from exc

    if log_events:
        logger.log(logging_level, f"Notified subscribers about event '{event}'.")


def subscribe(subscriber: Any, event: Event, callback: Callable) -> None:
    events_to_subscribers[event][subscriber] = callback

    if subscriber not in subscribers_to_events.keys():
        subscribers_to_events[subscriber] = [event]
    else:
        subscribers_to_events[subscriber].append(event)


def unsubscribe(subscriber: Any, event: Event) -> None:
    try:
        events_to_subscribers[event].pop(subscriber)
    except KeyError:
        logger.debug(f"Can't unsubscribe. '{subscriber} is a subscriber of {event}'")
        return

    subscribers_to_events[subscriber].remove(event)

    if not subscribers_to_events[subscriber]:
        subscribers_to_events.pop(subscriber)


def unsubscribe_from_all(subscriber: Any) -> None:
    if subscriber not in subscribers_to_events.keys():
        return

    for event in subscribers_to_events[subscriber].copy():
        unsubscribe(subscriber, event)
