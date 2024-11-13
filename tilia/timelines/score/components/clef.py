from __future__ import annotations
from typing import TYPE_CHECKING

from enum import Enum, auto

from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.validators import validate_time, validate_integer
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components.validators import validate_step

if TYPE_CHECKING:
    from tilia.timelines.score.timeline import ScoreTimeline


class Clef(TimelineComponent):
    SERIALIZABLE_BY_VALUE = ["time", "line_number", "step", "octave", "icon"]
    ORDERING_ATTRS = ("time",)

    KIND = ComponentKind.CLEF

    validators = {
        "timeline": lambda _: False,  # read-only
        "id": lambda _: False,  # read-only
        "time": validate_time,
        "line_number": validate_integer,
        "step": validate_step,
        "octave": validate_integer,
    }

    def __init__(
        self,
        timeline: ScoreTimeline,
        id: int,
        staff_index: int,
        time: float | None = None,
        line_number: int | None = None,
        step: int | None = None,
        octave: int | None = None,
        icon: str | None = None,
        shorthand: Shorthand | None = None,
    ):

        self.staff_index = staff_index
        self.time = time
        if shorthand:
            self.from_shorthand(shorthand)
        else:
            # Line number is relative to the central line, with negative numbers
            # being below the central line and positive numbers above.
            # e.g. In a treble clef, -1 is the second line in 2 is the fifth line.
            self.line_number = line_number
            self.step = step
            self.octave = octave
            self.icon = icon

        super().__init__(timeline, id)

    def central_step(self):
        return self.get_data('step') + self.get_data('line_number') * -2, self.get_data('octave')

    class Shorthand(Enum):
        BASS = auto()
        TREBLE = auto()
        TREBLE_8VB = auto()
        ALTO = auto()
        
    def from_shorthand(self, shorthand: Clef.Shorthand):
        if shorthand == Clef.Shorthand.BASS:
            self.line_number = 1
            self.step = 3
            self.octave = 2
            self.icon = "clef-bass.svg"
        elif shorthand == Clef.Shorthand.TREBLE:
            self.line_number = -1
            self.step = 4
            self.octave = 3
            self.icon = "clef-treble.svg"
        elif shorthand == Clef.Shorthand.TREBLE_8VB:
            self.line_number = -1
            self.step = 4
            self.octave = 2
            self.icon = "clef-treble-8vb.svg"
        elif shorthand == Clef.Shorthand.ALTO:
            self.line_number = 0
            self.step = 0
            self.octave = 3
            self.icon = "clef-alto.svg"
        else:
            raise ValueError(f"Invalid shorthand: {shorthand}")

    def shorthand(self) -> Clef.Shorthand | None:
        match self.line_number, self.step, self.octave:
            case 1, 3, 2:
                return Clef.Shorthand.BASS
            case -1, 4, 3:
                return Clef.Shorthand.TREBLE
            case -1, 4, 2:
                return Clef.Shorthand.TREBLE_8VB
            case 0, 0, 3:
                return Clef.Shorthand.ALTO
            case _:
                return None

    def __str__(self):
        return f"Clef({self.time}, {self.line_number}, {self.step}, {self.octave}, {self.icon})"
