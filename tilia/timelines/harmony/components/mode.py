from __future__ import annotations

from typing import TYPE_CHECKING

import music21

from tilia.timelines.base.component import PointLikeTimelineComponent
from tilia.timelines.base.validators import validate_string, validate_time
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.harmony.validators import (
    validate_accidental,
    validate_level,
    validate_mode_type,
    validate_step,
)

if TYPE_CHECKING:
    from tilia.timelines.harmony.timeline import HarmonyTimeline


class Mode(PointLikeTimelineComponent):
    SERIALIZABLE = ["time", "step", "accidental", "type", "comments", "level"]
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
        timeline: HarmonyTimeline,
        id: int,
        time: float = 0,
        step: int = 0,
        accidental: int = 0,
        type: str = "major",
        level: int = 2,
        comments: str = "",
        **_,
    ):
        self.time = time
        self.step = step
        self.accidental = accidental
        self.type = type
        self.level = level
        self.comments = comments

        super().__init__(timeline, id)

    def __str__(self):
        return f"Mode({self.step, self.accidental, self.type}) at {self.time}"

    def __repr__(self):
        return str(dict(self.__dict__.items()))

    @property
    def key(self):
        # TODO: these are local imports only because the constants live in the
        # UI folder and importing them at module level would cause a circular.
        # Move the constants out of `tilia/ui/` so this can become a top-level import.
        from tilia.ui.timelines.harmony.constants import INT_TO_NOTE_NAME, Accidental

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
    # TODO: these are local imports only because the constants live in the
    # UI folder and importing them at module level would cause a circular.
    # Move the constants out of `tilia/ui/` so this can become a top-level import.
    from tilia.ui.timelines.harmony.constants import NOTE_NAME_TO_INT

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
    # TODO: these are local imports only because the constants live in the
    # UI folder and importing them at module level would cause a circular.
    # Move the constants out of `tilia/ui/` so this can become a top-level import.
    from tilia.ui.timelines.harmony.constants import NOTE_NAME_TO_INT

    return {
        "step": NOTE_NAME_TO_INT[obj.tonic.step],
        "accidental": int(obj.tonic.alter),
        "type": obj.mode,
    }
