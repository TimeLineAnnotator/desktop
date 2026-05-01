from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.validators import (
    validate_pre_validated,
    validate_read_only,
)
from tilia.timelines.component_kinds import ComponentKind

if TYPE_CHECKING:
    from tilia.timelines.audiowave.timeline import AudioWaveTimeline


class Waveform(TimelineComponent):
    SERIALIZABLE = ["samplerate", "total_frames", "frames_per_peak"]
    ORDERING_ATTRS = tuple()

    KIND = ComponentKind.AUDIOWAVE

    validators = {
        "timeline": validate_read_only,
        "id": validate_read_only,
        "samplerate": validate_pre_validated,
        "total_frames": validate_pre_validated,
        "frames_per_peak": validate_pre_validated,
    }

    def __init__(
        self,
        timeline: AudioWaveTimeline,
        id: int,
        samplerate: int = 0,
        total_frames: int = 0,
        frames_per_peak: int = 128,
        **__,
    ):
        self.samplerate = int(samplerate)
        self.total_frames = int(total_frames)
        self.frames_per_peak = int(frames_per_peak)
        # runtime-only — populated by AudioWaveTimeline once peaks computed.
        self.lod_min: list[np.ndarray] = []
        self.lod_max: list[np.ndarray] = []
        self.is_ready: bool = False
        super().__init__(timeline, id)

    @property
    def duration_seconds(self) -> float:
        if not self.samplerate:
            return 0.0
        return self.total_frames / self.samplerate

    def __repr__(self):
        return (
            f"Waveform(samplerate={self.samplerate}, "
            f"total_frames={self.total_frames}, ready={self.is_ready})"
        )
