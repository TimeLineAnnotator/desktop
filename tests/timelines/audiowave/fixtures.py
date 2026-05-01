import functools

import numpy as np
import pytest

from tilia.requests import Post, post
from tilia.timelines.audiowave.timeline import AudioWaveTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind


@pytest.fixture
def audiowave_tl(tls):
    tl: AudioWaveTimeline = tls.create_timeline(TimelineKind.AUDIOWAVE_TIMELINE)
    # Block automatic peak computation; tests inject peaks via set_peaks_for_test.
    tl.refresh = lambda: None
    tl.clear()

    def set_peaks_for_test(samplerate=44100, total_frames=44100,
                           frames_per_peak=512,
                           peaks_min=None, peaks_max=None):
        component, _ = tl.create_component(
            ComponentKind.AUDIOWAVE,
            samplerate=samplerate,
            total_frames=total_frames,
            frames_per_peak=frames_per_peak,
        )
        if peaks_min is None:
            peaks_min = np.array([-0.5], dtype=np.float32)
        if peaks_max is None:
            peaks_max = np.array([0.5], dtype=np.float32)
        from tilia.timelines.audiowave.peaks import build_lod_pyramid
        component.lod_min, component.lod_max = build_lod_pyramid(peaks_min, peaks_max)
        component.is_ready = True
        return component

    tl.set_peaks_for_test = set_peaks_for_test
    return tl


@pytest.fixture
def audiowave_tlui(tilia, audiowave_tl, tluis):
    post(Post.APP_STATE_RECORD, "tlui fixture")
    ui = tluis.get_timeline_ui(audiowave_tl.id)
    ui.set_peaks_for_test = audiowave_tl.set_peaks_for_test
    return ui  # will be deleted by tls


@pytest.fixture
def waveform_component(audiowave_tl):
    return audiowave_tl.set_peaks_for_test()


@pytest.fixture
def waveform_element(audiowave_tlui, waveform_component):
    return audiowave_tlui.get_element(waveform_component.id)
