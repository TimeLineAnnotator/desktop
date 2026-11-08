"""A short tone for what's clicked in a score, as in a score editor. It goes
through an audio output of its own, so that it doesn't touch what the player
has loaded or where it is."""

from __future__ import annotations

from typing import Sequence

import numpy as np
from PySide6.QtCore import QBuffer, QByteArray, QIODevice
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSink

from tilia.media import synth

LENGTH = 0.8  # seconds


def render_tones(pitches: Sequence[float]) -> bytes:
    """The pitches sounding together, as mono 16-bit samples."""
    notes = [synth.SynthNote(0.0, LENGTH, pitch) for pitch in pitches]
    samples = synth.render(notes, LENGTH + synth.RELEASE)
    return (samples * np.iinfo(np.int16).max).astype(np.int16).tobytes()


def _get_format() -> QAudioFormat:
    audio_format = QAudioFormat()
    audio_format.setSampleRate(synth.SAMPLE_RATE)
    audio_format.setChannelCount(1)
    audio_format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    return audio_format


class Audition:
    def __init__(self) -> None:
        self._sink: QAudioSink | None = None
        self._buffer: QBuffer | None = None

    def play(self, pitches: Sequence[float], volume: int) -> None:
        """A new tone cuts off the last one. `volume` goes from 0 to 100, as
        the player's does."""
        self.stop()
        self._buffer = QBuffer()
        self._buffer.setData(QByteArray(render_tones(pitches)))
        self._buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        # A new one each time, as the default output device may have changed.
        self._sink = QAudioSink(_get_format())
        self._sink.stateChanged.connect(self._on_state_changed)
        self._sink.setVolume(
            QAudio.convertVolume(
                volume / 100.0,
                QAudio.VolumeScale.LinearVolumeScale,
                QAudio.VolumeScale.LogarithmicVolumeScale,
            )
        )
        self._sink.start(self._buffer)

    def stop(self) -> None:
        if self._sink:
            self._sink.stop()

    def _on_state_changed(self, state: QAudio.State) -> None:
        if state == QAudio.State.IdleState:
            # Done: let go of the device.
            self.stop()
