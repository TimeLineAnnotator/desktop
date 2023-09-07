from enum import auto, Enum


class PasteCardinality(Enum):
    MULTIPLE = auto()
    SINGLE = auto()


class PasteDestination(Enum):
    ELEMENTS = auto()
    TIMELINE = auto()
