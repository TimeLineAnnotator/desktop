from enum import Enum, auto


class TimelineSelector(Enum):
    ANY = auto()
    FROM_CLI = auto()
    FROM_MANAGE_TIMELINES_CURRENT = auto()
    FROM_MANAGE_TIMELINES_TO_PERMUTE = auto()
    FROM_CONTEXT_MENU = auto()
    FROM_CONTEXT_MENU_TO_PERMUTE = auto()
    EXPLICIT = auto()
    SELECTED = auto()
    ALL = auto()
    FIRST = auto()
    PASTE = auto()


class ElementSelector(Enum):
    SELECTED = auto()
    ALL = auto()
    NONE = auto()
