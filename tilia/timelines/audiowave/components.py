from __future__ import annotations

from typing import TYPE_CHECKING

from tilia.timelines.base.validators import (
    validate_time,
    validate_read_only,
    validate_pre_validated,
)
from tilia.timelines.component_kinds import ComponentKind

if TYPE_CHECKING:
    from tilia.timelines.audiowave.timeline import AudioWaveTimeline

from tilia.timelines.base.component import SegmentLikeTimelineComponent


class AmplitudeBar(SegmentLikeTimelineComponent):
    SERIALIZABLE_BY_VALUE = ["start", "end", "amplitude"]
    ORDERING_ATTRS = ("start",)

    KIND = ComponentKind.AUDIOWAVE

    validators = {
        "timeline": validate_read_only,
        "id": validate_read_only,
        "start": validate_time,
        "end": validate_time,
        "amplitude": validate_pre_validated,
    }

    def __init__(
        self,
        timeline: AudioWaveTimeline,
        id: int,
        start: float,
        end: float,
        amplitude: float,
        **__,
    ):
        self.start = start
        self.end = end
        self.amplitude = amplitude

        self.update_hash()

    def __repr__(self):
        return f"AudioWave({self.start}, {self.amplitude})"
