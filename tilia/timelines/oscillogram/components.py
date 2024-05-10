from __future__ import annotations

from typing import TYPE_CHECKING

from tilia.timelines.base.validators import validate_time, validate_read_only, validate_pre_validated
from tilia.timelines.component_kinds import ComponentKind

if TYPE_CHECKING:
    from tilia.timelines.oscillogram.timeline import OscillogramTimeline

from tilia.timelines.base.component import TimelineComponent

class Oscillogram(TimelineComponent):
    SERIALIZABLE_BY_VALUE = [
        "start",
        "length",
        "level"]
    ORDERING_ATTRS = ("start",)

    KIND = ComponentKind.OSCILLOGRAM

    validators = {
        "timeline": validate_read_only,
        "id": validate_read_only,
        "start": validate_time,
        "length": validate_time,
        "level": validate_pre_validated
    }

    def __init__(self, timeline: OscillogramTimeline, id: int, start: float, length: float, level: float, **__):
        super().__init__(timeline, id)

        self.start = start
        self.length = length
        self.level = level
    
    def __repr__(self):
        return f"Oscillogram({self.start}, {self.level})"
