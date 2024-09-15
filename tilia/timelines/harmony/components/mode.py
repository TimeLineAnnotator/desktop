from __future__ import annotations

import music21

from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.validators import validate_time, validate_string
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.harmony.validators import (
    validate_step,
    validate_accidental,
    validate_mode_type,
    validate_level,
)
from tilia.timelines.marker.timeline import MarkerTimeline
from tilia.ui.timelines.harmony.constants import (
    NOTE_NAME_TO_INT,
    INT_TO_NOTE_NAME,
    Accidental,
)


class Mode(TimelineComponent):
    SERIALIZABLE_BY_VALUE = ["time", "step", "accidental", "type", "comments", "level"]
    SERIALIZABLE_BY_ID = []
    SERIALIZABLE_BY_ID_LIST = []
    ORDERING_ATTRS = ("level", "time")
    KIND = ComponentKind.MODE

    validators = {
        "timeline": lambda _: False,
        "id": lambda _: False,
        "time": validate_time,
        "step": validate_step,
        "accidental": validate_accidental,
        "type": validate_mode_type,
        "comments": validate_string,
        "level": validate_level,
    }

    def __init__(
        self,
        timeline: MarkerTimeline,
        id: int,
        time: float = 0,
        step: int = 0,
        accidental: int = 0,
        type: str = "major",
        level: int = 2,
        comments: str = "",
    ):
        super().__init__(timeline, id)

        self.time = time
        self.step = step
        self.accidental = accidental
        self.type = type
        self.level = level
        self.comments = comments

    def __str__(self):
        return f"Mode({self.step, self.accidental, self.type}) at {self.time}"

    def __repr__(self):
        return str(dict(self.__dict__.items()))

    @property
    def key(self):
        tonic = INT_TO_NOTE_NAME[self.step]
        tonic_symbol = tonic.lower() if self.get_data("type") == "minor" else tonic
        accidental_symbol = Accidental.get_from_int(
            "music21", self.get_data("accidental")
        )
        return music21.key.Key(tonic_symbol + accidental_symbol)


def _format_postfix_accidental(text):
    if len(text) > 1 and text[1] == "b":
        text = text[0] + "-" + text[2:]
        if len(text) > 2 and text[2] == "b":
            text = text[:2] + "-" + text[3:]
    return text


def get_params_from_text(text):
    success, music21_object = _get_music21_object_from_text(text)
    if not success:
        return False, None

    return True, _get_params_from_music21_object(music21_object)


def _get_music21_object_from_text(text):
    text = _format_postfix_accidental(text)
    valid_initial_chars = list(NOTE_NAME_TO_INT) + list(
        map(str.lower, NOTE_NAME_TO_INT)
    )
    if text.startswith(tuple(valid_initial_chars)):
        try:
            return True, music21.key.Key(text)
        except ValueError:
            return False, None


def _get_params_from_music21_object(obj: music21.key.Key):
    return {
        "step": NOTE_NAME_TO_INT[obj.tonic.step],
        "accidental": int(obj.tonic.alter),
        "type": obj.mode,
    }
