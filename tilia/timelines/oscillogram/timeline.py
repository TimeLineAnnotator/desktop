from __future__ import annotations
from typing import TYPE_CHECKING

import pydub
import pydub.utils

from re import match

from tilia import settings
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.component_kinds import ComponentKind
from tilia.requests import get, Get
from tilia.timelines.base.timeline import TimelineComponentManager
from tilia.constants import YOUTUBE_URL_REGEX


class OscillogramTimeline(Timeline):
    KIND = TimelineKind.OSCILLOGRAM_TIMELINE
    DEFAULT_HEIGHT = settings.get("oscillogram_timeline", "default_height")
    
    component_manager: OscillogramTLComponentManager

    def _create_timeline(self):
        audio = self._get_audio()
        if not audio:
            return
        
        self.clear()    
        dt, normalised_amplitudes = self._get_normalised_amplitudes(audio)
        self._create_components(dt, normalised_amplitudes)

    def _get_audio(self):
        path = get(Get.MEDIA_PATH)
        if match(path, YOUTUBE_URL_REGEX):
            return None
        return pydub.AudioSegment.from_file(path)
    
    def _get_normalised_amplitudes(self, audio):    
        divisions = min([get(Get.PLAYBACK_AREA_WIDTH), settings.get("oscillogram_timeline", "max_div"), audio.frame_count()])
        dt = audio.duration_seconds / divisions
        chunks = pydub.utils.make_chunks(audio, dt * 1000)
        amplitude = [chunk.rms for chunk in chunks]
        return dt, [amp / max(amplitude) for amp in amplitude]
    
    def _create_components(self, duration: float, amplitudes: float):
        for i in range(len(amplitudes)):
            self.create_timeline_component(
                kind = ComponentKind.OSCILLOGRAM,
                start = i * duration,
                end = (i + 1) * duration,
                amplitude = amplitudes[i]
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
    