from __future__ import annotations

import hashlib

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


class Mode(TimelineComponent):
    SERIALIZABLE_BY_VALUE = ["time", "step", "accidental", "type", "comments", "level"]
    SERIALIZABLE_BY_ID = []
    SERIALIZABLE_BY_ID_LIST = []
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
        time: float,
        step: int,
        accidental: int,
        type: str,
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

    def __lt__(self, other):
        return self.time < other.time

    def __str__(self):
        return f"Mode({self.step, self.accidental, self.type}) at {self.time}"

    def __repr__(self):
        return str(dict(self.__dict__.items()))

    @classmethod
    def create(cls, *args, **kwargs):
        return Mode(*args, **kwargs)
