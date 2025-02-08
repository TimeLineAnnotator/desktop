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


class ScrollType(Enum):
    OFF = auto()
    BY_PAGE = auto()
    CONTINUOUS = auto()

    @classmethod
    def get_option_list(cls) -> list[str]:
        return [" ".join(x.lower().split("_")) for x in cls._member_names_]

    @classmethod
    def get_enum_from_str(cls, option: str):
        return cls["_".join(option.upper().split(" "))]

    @staticmethod
    def get_str_from_enum(option):
        return " ".join(option.name.title().split("_"))
