import os
import wave

import numpy as np
import pytest

from tilia.timelines.audiowave.peaks import (
    build_lod_pyramid,
    compute_peaks_sync,
)


def _write_test_wav(path: str, samples: np.ndarray, samplerate: int = 44100):
    samples = np.asarray(samples, dtype=np.float32)
    samples = np.clip(samples, -1.0, 1.0)
    int_samples = (samples * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(int_samples.tobytes())


class TestComputePeaksSync:
    def test_constant_signal(self, tmp_path):
        path = os.fspath(tmp_path / "constant.wav")
        # Two-bucket signal: first half +0.5, second half -0.5.
        samples = np.concatenate(
            [np.full(1024, 0.5, dtype=np.float32),
             np.full(1024, -0.5, dtype=np.float32)]
        )
        _write_test_wav(path, samples, samplerate=44100)

        mins, maxs, sr, total = compute_peaks_sync(path, frames_per_peak=1024)

        assert sr == 44100
        assert total == 2048
        assert mins.shape == (2,)
        assert maxs.shape == (2,)
        # Normalized so max(abs) == 1.0
        assert maxs[0] == pytest.approx(1.0, abs=1e-3)
        assert mins[0] == pytest.approx(1.0, abs=1e-3)
        assert mins[1] == pytest.approx(-1.0, abs=1e-3)
        assert maxs[1] == pytest.approx(-1.0, abs=1e-3)

    def test_returns_float32(self, tmp_path):
        path = os.fspath(tmp_path / "f.wav")
        _write_test_wav(path, np.zeros(2048, dtype=np.float32))
        mins, maxs, _, _ = compute_peaks_sync(path, frames_per_peak=1024)
        assert mins.dtype == np.float32
        assert maxs.dtype == np.float32


class TestBuildLodPyramid:
    def test_halves_each_level(self):
        mins = np.array([-0.1, -0.2, -0.3, -0.4, -0.5, -0.6, -0.7, -0.8],
                        dtype=np.float32)
        maxs = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
                        dtype=np.float32)
        lod_min, lod_max = build_lod_pyramid(mins, maxs)
        assert len(lod_min) == 4  # 8 -> 4 -> 2 -> 1
        assert lod_min[0].shape == (8,)
        assert lod_min[1].shape == (4,)
        assert lod_min[2].shape == (2,)
        assert lod_min[3].shape == (1,)

    def test_correctness_min_max_pairing(self):
        mins = np.array([-0.1, -0.5, -0.2, -0.3], dtype=np.float32)
        maxs = np.array([0.1, 0.5, 0.2, 0.3], dtype=np.float32)
        lod_min, lod_max = build_lod_pyramid(mins, maxs)
        np.testing.assert_allclose(lod_min[1], [-0.5, -0.3])
        np.testing.assert_allclose(lod_max[1], [0.5, 0.3])


class TestReduceatBoundary:
    """Regression: at certain zoom levels the per-pixel min/max aggregation
    used to build a reduceat index equal to ``len(lod_array)``, which numpy
    rejects with IndexError and which left QPainter in a corrupted state
    (subsequent paints could segfault).  Verify that reduceat tolerates
    every index produced by clipping into ``[0, n - 1]``.
    """

    def test_indices_at_array_length_are_safe(self):
        # A small LOD array; we explicitly construct indices that include
        # the maximum legal value (n - 1).
        a = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float32)
        idx = np.array([0, 2, 4, 4, 4], dtype=np.int64)
        # Should not raise.
        result = np.minimum.reduceat(a, idx)
        assert result.shape == (5,)


class TestLegacyTlaFormat:
    def test_legacy_amplitude_components_trigger_refresh(self, audiowave_tl):
        legacy = {
            1: {"start": 0.0, "end": 1.0, "amplitude": 0.5, "kind": "AUDIOWAVE"},
            2: {"start": 1.0, "end": 2.0, "amplitude": 0.7, "kind": "AUDIOWAVE"},
        }
        called = {"count": 0}

        original_refresh = audiowave_tl.refresh

        def tracking_refresh():
            called["count"] += 1

        audiowave_tl.refresh = tracking_refresh
        try:
            audiowave_tl.deserialize_components(legacy)
        finally:
            audiowave_tl.refresh = original_refresh

        assert called["count"] == 1
