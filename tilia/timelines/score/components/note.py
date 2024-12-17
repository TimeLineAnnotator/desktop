from enum import Enum, auto

from tilia.timelines.base.component import SegmentLikeTimelineComponent
from tilia.timelines.base.validators import (
    validate_time,
    validate_color,
    validate_string,
    validate_integer,
)
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components.validators import (
    validate_step,
    validate_accidental,
    validate_tie_type,
)
from tilia.timelines.score.timeline import ScoreTimeline

STEP_TO_PC = {0: 0, 1: 2, 2: 4, 3: 5, 4: 7, 5: 9, 6: 11}


def octave_to_pc(octave: int) -> int:
    return (octave - 3) * 12


class Note(SegmentLikeTimelineComponent):
    SERIALIZABLE_BY_VALUE = [
        "start",
        "end",
        "step",
        "accidental",
        "octave",
        "staff_index",
        "color",
        "comments",
        "display_accidental",
    ]
    SERIALIZABLE_BY_ID = []
    SERIALIZABLE_BY_ID_LIST = []
    ORDERING_ATTRS = ("start", "end", "pitch", "staff_index")

    KIND = ComponentKind.NOTE

    validators = {
        "timeline": lambda _: False,
        "id": lambda _: False,
        "start": validate_time,
        "end": validate_time,
        "step": validate_step,
        "tie": validate_tie_type,
        "accidental": validate_accidental,
        "octave": validate_integer,
        "staff_index": validate_integer,
        "color": validate_color,
        "comments": validate_string,
    }

    class TieType(Enum):
        START = auto()
        STOP = auto()
        NONE = auto()

    def __init__(
        self,
        timeline: ScoreTimeline,
        id: int,
        start: float,
        end: float,
        step: int,
        accidental: int,
        octave: int,
        staff_index: int,
        tie_type: TieType = TieType.NONE,
        display_accidental: bool = False,
        label="",
        color=None,
        comments="",
        **_,
    ):

        self.start = start
        self.end = end
        self.step = step
        self.accidental = accidental
        self.display_accidental = display_accidental
        self.octave = octave
        self.staff_index = staff_index
        self.tie_type = tie_type
        self.label = label
        self.color = color
        self.comments = comments
        # assumes start, end, octave, step, accidental and staff_index
        # won't change after instantiation
        self._ordinal = (start, end, octave, step, accidental, staff_index)

        super().__init__(timeline, id)

    def __str__(self):
        return f"Note({self.start, self.end, self.pitch, self.staff_index})"

    def __repr__(self):
        return str(dict(self.__dict__.items()))

    @property
    def ordinal(self):
        return self._ordinal

    @property
    def pitch_class(self):
        return pitch_class(self.step, self.accidental)

    @property
    def pitch(self):
        return pitch(self.step, self.accidental, self.octave)


def pitch(step, accidental, octave):
    return octave_to_pc(octave) + STEP_TO_PC[step] + accidental


def pitch_class(step, accidental):
    return (STEP_TO_PC[step] + accidental) % 12
