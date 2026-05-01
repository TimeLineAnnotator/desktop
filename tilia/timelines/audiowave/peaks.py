from __future__ import annotations

from typing import Callable

import numpy as np
import soundfile
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class CancelToken:
    def __init__(self):
        self.cancelled = False


def compute_peaks_sync(
    path: str,
    frames_per_peak: int,
    cancel: CancelToken | None = None,
) -> tuple[np.ndarray, np.ndarray, int, int]:
    """Read the audio file at ``path`` and compute per-bucket min/max peaks.

    Returns ``(peaks_min, peaks_max, samplerate, total_frames)`` where the
    peaks are normalized to [-1, 1] across the file.
    """
    with soundfile.SoundFile(path) as af:
        samplerate = af.samplerate
        total_frames = af.frames
        n_buckets = max(1, total_frames // frames_per_peak)

        peaks_min = np.zeros(n_buckets, dtype=np.float32)
        peaks_max = np.zeros(n_buckets, dtype=np.float32)

        for i, block in enumerate(
            af.blocks(blocksize=frames_per_peak, always_2d=True)
        ):
            if i >= n_buckets:
                break
            if cancel is not None and cancel.cancelled:
                return peaks_min, peaks_max, samplerate, total_frames
            mono = block.mean(axis=1) if block.shape[1] > 1 else block[:, 0]
            if mono.size == 0:
                continue
            peaks_min[i] = mono.min()
            peaks_max[i] = mono.max()

    abs_peak = max(
        float(np.abs(peaks_min).max(initial=0.0)),
        float(np.abs(peaks_max).max(initial=0.0)),
    )
    if abs_peak > 0:
        peaks_min = peaks_min / abs_peak
        peaks_max = peaks_max / abs_peak

    return (
        peaks_min.astype(np.float32),
        peaks_max.astype(np.float32),
        samplerate,
        total_frames,
    )


def build_lod_pyramid(
    peaks_min: np.ndarray, peaks_max: np.ndarray
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    """Build a power-of-two min/max LOD pyramid from base-level peaks.

    Level 0 is the base; each next level has half the length, taking
    pairwise minimum-of-mins and maximum-of-maxes.
    """
    lod_min = [peaks_min]
    lod_max = [peaks_max]
    cur_min, cur_max = peaks_min, peaks_max
    while len(cur_min) > 1:
        n = len(cur_min) // 2
        if n == 0:
            break
        new_min = np.minimum(cur_min[: n * 2 : 2], cur_min[1 : n * 2 : 2])
        new_max = np.maximum(cur_max[: n * 2 : 2], cur_max[1 : n * 2 : 2])
        lod_min.append(new_min)
        lod_max.append(new_max)
        cur_min, cur_max = new_min, new_max
    return lod_min, lod_max


class _PeaksWorkerSignals(QObject):
    done = Signal(object, object, int, int)
    error = Signal(object)


class _PeaksRunnable(QRunnable):
    def __init__(
        self,
        path: str,
        frames_per_peak: int,
        signals: _PeaksWorkerSignals,
        cancel: CancelToken,
    ):
        super().__init__()
        self.path = path
        self.frames_per_peak = frames_per_peak
        self.signals = signals
        self.cancel = cancel

    def run(self) -> None:
        try:
            mins, maxs, samplerate, total_frames = compute_peaks_sync(
                self.path, self.frames_per_peak, self.cancel
            )
        except Exception as exc:
            if not self.cancel.cancelled:
                self.signals.error.emit(exc)
            return
        if self.cancel.cancelled:
            return
        self.signals.done.emit(mins, maxs, samplerate, total_frames)


def compute_peaks_async(
    path: str,
    frames_per_peak: int,
    on_done: Callable[[np.ndarray, np.ndarray, int, int], None],
    on_error: Callable[[Exception], None] | None = None,
) -> tuple[CancelToken, _PeaksWorkerSignals]:
    """Submit a peak-computation runnable to the global QThreadPool.

    Returns ``(cancel_token, signals)``. The caller should keep the
    ``signals`` reference alive (it owns the slot connection); setting
    ``cancel_token.cancelled = True`` causes the worker to exit early
    without firing callbacks.
    """
    cancel = CancelToken()
    signals = _PeaksWorkerSignals()

    def _on_done(mins, maxs, samplerate, total_frames):
        if cancel.cancelled:
            return
        on_done(mins, maxs, samplerate, total_frames)

    def _on_error(exc):
        if cancel.cancelled:
            return
        if on_error is not None:
            on_error(exc)

    signals.done.connect(_on_done)
    signals.error.connect(_on_error)

    QThreadPool.globalInstance().start(
        _PeaksRunnable(path, frames_per_peak, signals, cancel)
    )

    return cancel, signals
