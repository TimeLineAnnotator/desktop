from enum import Enum, auto


class ModifierEnum(Enum):
    NONE = auto()
    CONTROL = auto()
    SHIFT = auto()
    ALT = auto()
    CONTROL_SHIFT = auto()
    CONTROL_ALT = auto()
    SHIFT_ALT = auto()
    CONTROL_SHIFT_ALT = auto()
