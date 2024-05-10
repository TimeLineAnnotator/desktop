from __future__ import annotations
from typing import TYPE_CHECKING

import pydub
import pydub.utils

from tilia import settings
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.component_kinds import ComponentKind
from tilia.requests import get, Get
from tilia.timelines.base.timeline import TimelineComponentManager

if TYPE_CHECKING:
    from tilia.timelines.base.component import TimelineComponent


class OscillogramTimeline(Timeline):
    KIND = TimelineKind.OSCILLOGRAM_TIMELINE
    DEFAULT_HEIGHT = settings.get("oscillogram_timeline", "default_height")
    
    component_manager: OscillogramTLComponentManager

    def _create_timeline(self):
        if self.components and len(self.components) == settings.get("oscillogram_timeline", "max_div"):
            return
        try:
            audio = pydub.AudioSegment.from_file(get(Get.MEDIA_PATH))
        except:
            return
        else:
            divisions = min([get(Get.PLAYBACK_AREA_WIDTH), settings.get("oscillogram_timeline", "max_div"), audio.frame_count()])
            if divisions == len(self.components):
                return
            self.clear()
            dt = audio.duration_seconds / divisions
            chunks = pydub.utils.make_chunks(audio, dt * 1000)
            amplitude = [chunk.rms for chunk in chunks]
            normalised = [amp / max(amplitude) for amp in amplitude]
            for i in range(len(normalised)):
                self.create_timeline_component(
                    kind = ComponentKind.OSCILLOGRAM,
                    start = i * dt,
                    length = dt,
                    level = normalised[i]
                )

    def refresh(self):
        self._create_timeline()

    def crop(self, *_):
        self._create_timeline()

    def scale(self, *_):
        self._create_timeline()

class OscillogramTLComponentManager(TimelineComponentManager):
    COMPONENT_TYPES = [ComponentKind.OSCILLOGRAM]

    def __init__(self):
        super().__init__(self.COMPONENT_TYPES)
    