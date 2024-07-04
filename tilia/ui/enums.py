from enum import auto, Enum


class PasteCardinality(Enum):
    MULTIPLE = auto()
    SINGLE = auto()


class PasteDestination(Enum):
    ELEMENTS = auto()
    TIMELINE = auto()


class WindowState(Enum):
    OPENED = auto()
    CLOSED = auto()
    DELETED = auto()
    UPDATE = auto()
