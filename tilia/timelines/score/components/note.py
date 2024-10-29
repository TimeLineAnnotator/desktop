from tilia.timelines.base.component import SegmentLikeTimelineComponent
from tilia.timelines.base.validators import validate_time, validate_color, validate_string, validate_integer
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components.validators import validate_step, validate_accidental
from tilia.timelines.score.timeline import ScoreTimeline

STEP_TO_PC = {
    0: 0,
    1: 2,
    2: 4,
    3: 5,
    4: 7,
    5: 9,
    6: 11
}

OCTAVE_TO_PC = {
    0: -36,
    1: -24,
    2: -12,
    3: 0,
    4: 12,
    5: 24,
    6: 36
}


class Note(SegmentLikeTimelineComponent):
    SERIALIZABLE_BY_VALUE = ["start", "end", "step", "accidental", "octave", "color", "comments", "display_accidental"]
    SERIALIZABLE_BY_ID = []
    SERIALIZABLE_BY_ID_LIST = []
    ORDERING_ATTRS = ("start", "end", "pitch")

    KIND = ComponentKind.NOTE

    validators = {
        "timeline": lambda _: False,
        "id": lambda _: False,
        "start": validate_time,
        "end": validate_time,
        "step": validate_step,
        "accidental": validate_accidental,
        "octave": validate_integer,
        "color": validate_color,
        "comments": validate_string,
    }

    def __init__(
        self,
        timeline: ScoreTimeline,
        id: int,
        start: float,
        end: float,
        step: int,
        accidental: int,
        octave: int,
        display_accidental: bool = False,
        label="",
        color=None,
        comments="",
        **_,
    ):
        super().__init__(timeline, id)

        self.start = start
        self.end = end
        self.step = step
        self.accidental = accidental
        self.display_accidental = display_accidental
        self.octave = octave
        self.label = label
        self.color = color
        self.comments = comments

    def __str__(self):
        return f"Note({self.start, self.end, })"

    def __repr__(self):
        return str(dict(self.__dict__.items()))

    @property
    def pitch_class(self):
        return pitch_class(self.step, self.accidental)

    @property
    def pitch(self):
        return pitch(self.step, self.accidental, self.octave)


def pitch(step, accidental, octave):
    return OCTAVE_TO_PC[octave] + STEP_TO_PC[step] + accidental


def pitch_class(step, accidental):
    return (STEP_TO_PC[step] + accidental) % 12
