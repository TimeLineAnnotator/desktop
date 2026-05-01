from __future__ import annotations

import numpy as np
import soundfile

import tilia.errors
from tilia.requests import Get, Post, get, post
from tilia.settings import settings
from tilia.timelines.audiowave.peaks import (
    CancelToken,
    build_lod_pyramid,
    compute_peaks_async,
)
from tilia.timelines.base.timeline import (
    Timeline,
    TimelineComponentManager,
    TimelineFlag,
)
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind


class AudioWaveTLComponentManager(TimelineComponentManager):
    def __init__(self, timeline: AudioWaveTimeline):
        super().__init__(timeline, [ComponentKind.AUDIOWAVE])


class AudioWaveTimeline(Timeline):
    KIND = TimelineKind.AUDIOWAVE_TIMELINE
    COMPONENT_MANAGER_CLASS = AudioWaveTLComponentManager
    FLAGS = [
        TimelineFlag.NOT_CLEARABLE,
        TimelineFlag.NOT_EXPORTABLE,
        TimelineFlag.COMPONENTS_NOT_EDITABLE,
        TimelineFlag.COMPONENTS_NOT_DELETABLE,
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pending_cancel: CancelToken | None = None
        # `_pending_signals` keeps the QObject alive so its signal->slot
        # connection survives until the worker emits.
        self._pending_signals = None

    @property
    def default_height(self):
        return settings.get("audiowave_timeline", "default_height")

    @property
    def frames_per_peak(self) -> int:
        try:
            return int(settings.get("audiowave_timeline", "frames_per_peak"))
        except KeyError:
            return 512

    @property
    def waveform_component(self):
        components = self.components
        return components[0] if components else None

    def refresh(self):
        self._cancel_pending_computation()
        self.clear()

        path = get(Get.MEDIA_PATH)
        if not path:
            self._update_visibility(False)
            return

        try:
            with soundfile.SoundFile(path) as af:
                samplerate = af.samplerate
                total_frames = af.frames
        except Exception:
            tilia.errors.display(tilia.errors.AUDIOWAVE_INVALID_FILE)
            self._update_visibility(False)
            return

        self._update_visibility(True)
        component, _ = self.create_component(
            ComponentKind.AUDIOWAVE,
            samplerate=samplerate,
            total_frames=total_frames,
            frames_per_peak=self.frames_per_peak,
        )
        if component is None:
            return
        self._launch_peak_computation(path, component)

    def _launch_peak_computation(self, path: str, component) -> None:
        cancel, signals = compute_peaks_async(
            path,
            component.frames_per_peak,
            on_done=lambda mins, maxs, sr, tf: self._on_peaks_ready(
                component, mins, maxs, sr, tf
            ),
            on_error=lambda exc: self._on_peaks_error(),
        )
        self._pending_cancel = cancel
        self._pending_signals = signals

    def _on_peaks_ready(
        self,
        component,
        peaks_min: np.ndarray,
        peaks_max: np.ndarray,
        samplerate: int,
        total_frames: int,
    ) -> None:
        if component not in self.components:
            return
        component.samplerate = int(samplerate)
        component.total_frames = int(total_frames)
        component.lod_min, component.lod_max = build_lod_pyramid(
            peaks_min, peaks_max
        )
        component.is_ready = True
        post(Post.AUDIOWAVE_PEAKS_READY, self.id, component.id)

    def _on_peaks_error(self) -> None:
        tilia.errors.display(tilia.errors.AUDIOWAVE_INVALID_FILE)
        self._update_visibility(False)

    def _cancel_pending_computation(self) -> None:
        if self._pending_cancel is not None:
            self._pending_cancel.cancelled = True
        self._pending_cancel = None
        self._pending_signals = None

    def deserialize_components(self, components):
        is_legacy = any(
            isinstance(c, dict) and "amplitude" in c
            for c in components.values()
        )
        if is_legacy:
            self.refresh()
            return
        super().deserialize_components(components)
        path = get(Get.MEDIA_PATH)
        component = self.waveform_component
        if component is not None and path:
            self._launch_peak_computation(path, component)

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
