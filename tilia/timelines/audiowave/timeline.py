from __future__ import annotations

import pydub
import pydub.exceptions
import pydub.utils

from tilia import settings
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.component_kinds import ComponentKind
from tilia.requests import get, Get, post, Post
from tilia.timelines.base.timeline import TimelineComponentManager


class AudioWaveTimeline(Timeline):
    KIND = TimelineKind.AUDIOWAVE_TIMELINE
    DEFAULT_HEIGHT = settings.get("audiowave_timeline", "default_height")
    
    component_manager: AudioWaveTLComponentManager

    def _create_timeline(self, audio):
        dt, normalised_amplitudes = self._get_normalised_amplitudes(audio)
        self._create_components(dt, normalised_amplitudes)

    def _get_audio(self):
        path = get(Get.MEDIA_PATH)
        try:
            return pydub.AudioSegment.from_file(path)        
        except:
            post(Post.DISPLAY_ERROR, "AudioWave", "Cannot show AudioWave on selected file")
            return None
    
    def _get_normalised_amplitudes(self, audio):    
        divisions = min([get(Get.PLAYBACK_AREA_WIDTH), settings.get("audiowave_timeline", "max_div"), audio.frame_count()])
        dt = audio.duration_seconds / divisions
        chunks = pydub.utils.make_chunks(audio, dt * 1000)
        amplitude = [chunk.rms for chunk in chunks]
        return dt, [amp / max(amplitude) for amp in amplitude]
    
    def _create_components(self, duration: float, amplitudes: float):
        for i in range(len(amplitudes)):
            self.create_timeline_component(
                kind = ComponentKind.AUDIOWAVE,
                start = i * duration,
                end = (i + 1) * duration,
                amplitude = amplitudes[i]
            )

    def refresh(self):       
        self.clear()
        audio = self._get_audio()
        if not audio:
            post(Post.TIMELINE_DELETE_DONE, self.id)
            return
        
        self._create_timeline(audio)


class AudioWaveTLComponentManager(TimelineComponentManager):
    COMPONENT_TYPES = [ComponentKind.AUDIOWAVE]

    def __init__(self):
        super().__init__(self.COMPONENT_TYPES)
