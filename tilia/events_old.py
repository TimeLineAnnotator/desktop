"""
Implements a subscriber/publisher sytem for the app.
A Subscriber subclass may subscribe to events with a certain EventName via the Subscriber constructor (or the subscriber function).
Every time an event to which the subscriber has subscriber is posted via the 'post' function,
the subscriber gets notified through a call to its subscriber_react method.
"""


import logging
from enum import Enum, auto

from abc import ABC
from abc import abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class EventName(Enum):
    METADATA_NEW_FIELDS = auto()
    METADATA_WINDOW_OPENED = None
    METADATA_FIELD_EDITED = auto()
    UI_REQUEST_WINDOW_METADATA = auto()
    PLAYER_REQUEST_TO_SEEK_IF_NOT_PLAYING = auto()
    RIGHT_CLICK_MENU_NEW = auto()
    CANVAS_RIGHT_CLICK = auto()
    RIGHT_CLICK_MENU_OPTION_CLICK = auto()
    KEY_PRESS_RIGHT = auto()
    KEY_PRESS_LEFT = auto()
    KEY_PRESS_ENTER = auto()
    REQUEST_TO_REDO = auto()
    REQUEST_TO_UNDO = auto()
    KEY_PRESS_CONTROL_SHIFT_V = auto()
    UI_REQUEST_TO_DISPLAY_ERROR = auto()
    KEY_PRESS_CONTROL_V = auto()
    KEY_PRESS_CONTROL_C = auto()
    TIMELINE_COMPONENT_COPIED = auto()
    UI_REQUEST_WINDOW_ABOUT = auto()
    TIMELINES_REQUEST_TO_CLEAR_ALL_TIMELINES = auto()
    UI_REQUEST_WINDOW_DEVELOPMENT = auto()
    TIMELINES_REQUEST_TO_HIDE_TIMELINE = auto()
    TIMELINES_REQUEST_TO_SHOW_TIMELINE = auto()
    TIMELINES_REQUEST_TO_CLEAR_TIMELINE = auto()
    TIMELINES_REQUEST_TO_DELETE_TIMELINE = auto()
    TIMELINES_REQUEST_MOVE_DOWN_IN_DISPLAY_ORDER = auto()
    TIMELINES_REQUEST_MOVE_UP_IN_DISPLAY_ORDER = auto()
    UI_REQUEST_WINDOW_MANAGE_TIMELINES = auto()
    UI_REQUEST_WINDOW_INSPECTOR = auto()
    ADD_RANGE_BUTTON = auto()
    APP_ADD_TIMELINE = auto()
    APP_REQUEST_TO_CLOSE = auto()
    CANVAS_LEFT_CLICK = auto()
    CREATE_RANGE_FROM_BUTTON = auto()
    DEBUG_SELECTED_ELEMENTS = auto()
    DELETE_RANGE_BUTTON = auto()
    DESELECTED_OBJECT = auto()
    ENTER_PRESSED = auto()
    EXPLORER_AUDIO_INFO_FROM_SEARCH_RESULT = auto()
    EXPLORER_DISPLAY_SEARCH_RESULTS = auto()
    EXPLORER_LOAD_MEDIA = auto()
    EXPLORER_PLAY = auto()
    EXPLORER_SEARCH = auto()
    FILE_REQUEST_NEW_FILE = auto()
    FILE_REQUEST_TO_LOAD_MEDIA = auto()
    FILE_REQUEST_TO_OPEN = auto()
    FILE_REQUEST_TO_SAVE = auto()
    FOCUS_TIMELINES = auto()
    FREEZE_LABELS_SET = auto()
    HIERARCHY_TOOLBAR_BUTTON_PRESS_CREATE_CHILD = auto()
    HIERARCHY_TOOLBAR_BUTTON_PRESS_DELETE = auto()
    HIERARCHY_TOOLBAR_BUTTON_PRESS_GROUP = auto()
    HIERARCHY_TOOLBAR_BUTTON_PRESS_LEVEL_DECREASE = auto()
    HIERARCHY_TOOLBAR_BUTTON_PRESS_LEVEL_INCREASE = auto()
    HIERARCHY_TOOLBAR_BUTTON_PRESS_MERGE = auto()
    HIERARCHY_TOOLBAR_BUTTON_PRESS_PASTE_UNIT = auto()
    HIERARCHY_TOOLBAR_BUTTON_PRESS_PASTE_UNIT_WITH_CHILDREN = auto()
    HIERARCHY_TOOLBAR_BUTTON_PRESS_SPLIT = auto()
    INSPECTABLE_ELEMENT_DESELECTED = auto()
    INSPECTABLE_ELEMENT_SELECTED = auto()
    INSPECTOR_FIELD_EDITED = auto()
    INSPECTOR_WINDOW_CLOSED = auto()
    INSPECTOR_WINDOW_OPENED = auto()
    JOIN_RANGE_BUTTON = auto()
    KEY_PRESS_DELETE = auto()
    LEFT_BUTTON_CLICK = auto()
    MENU_OPTION_FILE_LOAD_MEDIA = auto()
    MERGE_RANGE_BUTTON = auto()
    PLAYER_AUDIO_TIME_CHANGE = auto()
    PLAYER_CHANGE_TO_AUDIO_PLAYER = auto()
    PLAYER_CHANGE_TO_VIDEO_PLAYER = auto()
    PLAYER_MEDIA_LOADED = auto()
    PLAYER_MEDIA_UNLOADED = auto()
    PLAYER_PAUSED = auto()
    PLAYER_REQUEST_TO_LOAD_MEDIA = auto()
    PLAYER_REQUEST_TO_PLAYPAUSE = auto()
    PLAYER_REQUEST_TO_SEEK = auto()
    PLAYER_REQUEST_TO_STOP = auto()
    PLAYER_REQUEST_TO_UNLOAD_MEDIA = auto()
    PLAYER_STOPPED = auto()
    PLAYER_STOPPING = auto()
    PLAYER_UNPAUSED = auto()
    RECORD_STATE = auto()
    REQUEST_AUTO_SAVE_START = auto()
    REQUEST_MERGE = auto()
    REQUEST_TIMELINES__LOAD_TIMELINE = auto()
    REQUEST_TIMELINE_FRONTEND__RESET_TIMELINE_SIZE = auto()
    REQUEST_ZOOM_IN = auto()
    REQUEST_ZOOM_OUT = auto()
    SEEK_TO_OBJECT_BFR = auto()
    SELECTED_OBJECT = auto()
    SPLIT_RANGE_BUTTON = auto()
    TIMELINE_COMPONENT_DESELECTED = auto()
    TIMELINE_COMPONENT_SELECTED = auto()
    TIMELINE_LEFT_BUTTON_DRAG = auto()
    TIMELINE_LEFT_BUTTON_RELEASE = auto()
    TIMELINE_LEFT_CLICK = auto()
    TIMELINE_LEFT_RELEASED = auto()
    TIMELINE_MOUSE_DRAG = auto()
    TIMELINE_PREPARING_TO_DRAG = auto()


class Event:
    def __init__(self, event_name: EventName):
        self.name = event_name
        self.subscribers = set()

    def attach(self, subscriber: object):
        self.subscribers.add(subscriber)

    def detach(self, subscriber: object):
        self.subscribers.remove(subscriber)

    def notify(self, *args, **kwargs):
        logger.debug(f"Notifying subscribers about event '{self.name}'...")
        if self.subscribers:
            for subscriber in self.subscribers.copy():
                logger.debug(f"Notifying {subscriber}...")
                subscriber.on_subscribed_event(self.name, *args, **kwargs)
            logger.debug(f"Notified subscribers about event '{self.name}'.")
        else:
            logger.debug(f"No subscribers attached to event.")


active_events = set()

_subscribers_to_subscriptions = {}

for event_name in EventName:
    active_events.add(Event(event_name))


def post(event_name: EventName, *args, **kwargs) -> None:
    try:
        logger.debug(f"Posting event {event_name.name} with {args=} and {kwargs=}.")
        event = find_event_by_name(event_name)
        event.notify(*args, **kwargs)
    except StopIteration:
        raise ValueError(f"No event named {event_name.name}. Can't post.")


def subscribe(event_name: EventName, subscriber):
    try:
        event = find_event_by_name(event_name)
    except StopIteration:
        raise ValueError(f"Can't subscribe: no registered event named {event_name}. ")

    event.attach(subscriber)
    subscriber.record_subscription(event_name)


def unsubscribe(event_name: EventName, subscriber):
    try:
        event = find_event_by_name(event_name)
    except StopIteration:
        raise ValueError(f"Can't unsubscribe: no registered event named {event_name}. ")

    event.detach(subscriber)


def find_event_by_name(event_name: EventName):
    return next(e for e in active_events if e.name == event_name)



class Subscriber(ABC):
    def __init__(
        self, *args, subscriptions: Optional[list[EventName]] = None, **kwargs
    ):
        super().__init__(*args, **kwargs)

        self._subs = set()

        if subscriptions:
            for item in subscriptions:
                subscribe(item, self)

    @abstractmethod
    def on_subscribed_event(
        self, event_name: EventName, *args: tuple, **kwargs: dict
    ) -> None:
        ...

    def unsubscribe(self, subscriptions: list | set) -> None:
        for event_str in subscriptions:
            logger.debug(f"Unsubscribing {self} from {event_str}.")
            unsubscribe(event_str, self)
            self._subs.remove(event_str)

    def unsubscribe_from_all(self) -> None:
        self.unsubscribe(self._subs.copy())

    def record_subscription(self, event_name) -> None:
        self._subs.add(event_name)



