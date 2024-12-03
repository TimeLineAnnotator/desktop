from __future__ import annotations

import functools
from typing import TYPE_CHECKING

from tilia.timelines.base.component import PointLikeTimelineComponent
from tilia.timelines.base.validators import validate_integer, validate_time, validate_non_negative_integer
from tilia.timelines.component_kinds import ComponentKind

if TYPE_CHECKING:
    from tilia.timelines.score.timeline import ScoreTimeline


class KeySignature(PointLikeTimelineComponent):
    KIND = ComponentKind.KEY_SIGNATURE
    SERIALIZABLE_BY_VALUE = ['staff_index', 'time', 'fifths']

    def __init__(self, timeline: ScoreTimeline, id: int, staff_index: int, time: float, fifths: int):
        self.validators |= {'staff_index': validate_non_negative_integer, 'time': validate_time, 'fifths': functools.partial(validate_integer, min=-7, max=7)}

        self.staff_index = staff_index
        self.time = time
        self.fifths = fifths

        super().__init__(timeline, id)

    def __str__(self):
        return f"KeySignature({self.time}, {self.fifths})"