from __future__ import annotations

import numpy as np
import soundfile

from tilia.settings import settings
from tilia.timelines.base.timeline import Timeline, TimelineFlag
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.component_kinds import ComponentKind
from tilia.requests import get, Get, post, Post
from tilia.timelines.base.timeline import TimelineComponentManager
import tilia.errors


class AudioWaveTLComponentManager(TimelineComponentManager):
    def __init__(self, timeline: AudioWaveTimeline):
        super().__init__(timeline, [ComponentKind.AUDIOWAVE])


class AudioWaveTimeline(Timeline):
    KIND = TimelineKind.AUDIOWAVE_TIMELINE
    COMPONENT_MANAGER_CLASS = AudioWaveTLComponentManager
    FLAGS = [TimelineFlag.NOT_CLEARABLE, TimelineFlag.NOT_EXPORTABLE]

    @property
    def default_height(self):
        return settings.get("audiowave_timeline", "default_height")

    def _create_timeline(self):
        dt, normalised_amplitudes = self._get_normalised_amplitudes()
        self._create_components(dt, normalised_amplitudes)

    def _get_audio(self):
        path = get(Get.MEDIA_PATH)
        try:
            return soundfile.SoundFile(path)
        except Exception:
            tilia.errors.display(tilia.errors.AUDIOWAVE_INVALID_FILE)
            return None

    def _get_normalised_amplitudes(self):
        divisions = min(
            [
                get(Get.PLAYBACK_AREA_WIDTH),
                settings.get("audiowave_timeline", "max_divisions"),
                self.audio.frames,
            ]
        )
        dt = self.audio.frames / self.audio.samplerate / divisions
        amplitude = [
            np.sqrt(np.mean(chunk**2))
            for chunk in self.audio.blocks(self.audio.frames // divisions)
        ]
        return dt, [amp / max(amplitude) for amp in amplitude]

    def _create_components(self, duration: float, amplitudes: list[float]):
        for i, amplitude in enumerate(amplitudes):
            self.create_component(
                kind=ComponentKind.AUDIOWAVE,
                start=i * duration,
                end=(i + 1) * duration,
                amplitude=amplitude,
            )

    def refresh(self):
        self.clear()
        self.audio = self._get_audio()
        if not self.audio:
            self._update_visibility(False)
            return
        self._update_visibility(True)
        self._create_timeline()

    def _update_visibility(self, is_visible: bool):
        if self.get_data("is_visible") != is_visible:
            self.set_data("is_visible", is_visible)
            post(Post.TIMELINE_SET_DATA_DONE, self.id, "is_visible", is_visible)

    def scale(self, factor: float) -> None:
        # refresh will be called when new media is loaded
        pass

    def crop(self, factor: float) -> None:
        # refresh will be called when new media is loaded
        pass
