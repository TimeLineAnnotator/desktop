from __future__ import annotations

import numpy as np
import soundfile

import tilia.errors
from tilia.requests import Get, LongOperation, Post, get, post
from tilia.settings import settings
from tilia.timelines.base.timeline import (
    Timeline,
    TimelineComponentManager,
    TimelineFlag,
)
from tilia.timelines.component_kinds import ComponentKind
from tilia.ui.background_task import run_in_background


def _compute_normalised_amplitudes(
    audio: soundfile.SoundFile, divisions: int
) -> tuple[float, list[float]]:
    """Runs on a worker thread -- must not call post()/get() or touch Qt."""
    dt = audio.frames / audio.samplerate / divisions
    amplitude = [
        np.sqrt(np.mean(chunk**2))
        for chunk in audio.blocks(audio.frames // divisions)
    ]
    return dt, [amp / max(amplitude) for amp in amplitude]


class AudioWaveTLComponentManager(TimelineComponentManager):
    def __init__(self, timeline: AudioWaveTimeline):
        super().__init__(timeline, [ComponentKind.AUDIOWAVE])


class AudioWaveTimeline(Timeline):
    COMPONENT_MANAGER_CLASS = AudioWaveTLComponentManager
    FLAGS = [
        TimelineFlag.NOT_CLEARABLE,
        TimelineFlag.NOT_EXPORTABLE,
        TimelineFlag.COMPONENTS_NOT_EDITABLE,
    ]

    @property
    def default_height(self):
        return settings.get("audiowave_timeline", "default_height")

    def _create_timeline(self):
        # Cast to int: Get.PLAYBACK_AREA_WIDTH can be a float (widget
        # geometry), but audio.blocks() below requires an int blocksize.
        divisions = int(
            min(
                [
                    get(Get.PLAYBACK_AREA_WIDTH),
                    settings.get("audiowave_timeline", "max_divisions"),
                    self.audio.frames,
                ]
            )
        )
        audio = self.audio

        post(
            Post.LONG_OPERATION, LongOperation.STARTED, "Creating audiowave timeline..."
        )

        def on_done(result: tuple[float, list[float]]) -> None:
            dt, normalised_amplitudes = result
            self._create_components(dt, normalised_amplitudes)
            post(Post.LONG_OPERATION, LongOperation.DONE)

        def on_error(_exc: Exception) -> None:
            post(Post.LONG_OPERATION, LongOperation.DONE)
            self._update_visibility(False)
            tilia.errors.display(tilia.errors.AUDIOWAVE_INVALID_FILE)

        run_in_background(
            lambda: _compute_normalised_amplitudes(audio, divisions),
            on_done=on_done,
            on_error=on_error,
        )

    def _get_audio(self):
        path = get(Get.MEDIA_PATH)
        try:
            return soundfile.SoundFile(path)
        except Exception:
            tilia.errors.display(tilia.errors.AUDIOWAVE_INVALID_FILE)
            return None

    def _create_components(self, duration: float, amplitudes: list[float]):
        total = len(amplitudes)
        for i, amplitude in enumerate(amplitudes):
            self.create_component(
                kind=ComponentKind.AUDIOWAVE,
                start=i * duration,
                end=(i + 1) * duration,
                amplitude=amplitude,
            )
            post(Post.LONG_OPERATION, LongOperation.PROGRESS, i + 1, total)

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
