"""Audio for a score: its notes rendered with a simple additive synth.

It lets a score be heard when no media is loaded. Pitches are exact, quarter
tones and any other microtones included, which MIDI and its synths can only
approximate with pitch bends. The tone is plain on purpose, organ-like with a
soft attack, so that chords and their pitch classes are easy to hear out.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import soundfile

from tilia.requests import Get, get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components.note import Note
from tilia.timelines.score.timeline import ScoreTimeline

SAMPLE_RATE = 44100
# Partials' amplitudes, from the fundamental up.
PARTIALS = (1.0, 0.45, 0.25, 0.12, 0.06)
ATTACK = 0.01  # seconds
RELEASE = 0.08  # seconds, after a note's end
# How much of a note's loudness stays after its first decay.
SUSTAIN = 0.35
DECAY_RATE = 3.0  # per second
PEAK = 0.8
A4_PITCH = 69  # MIDI note number
A4_FREQUENCY = 440.0


@dataclass(frozen=True)
class SynthNote:
    start: float  # seconds
    end: float  # seconds
    # In semitones, as MIDI numbers them (60 is middle C), and fractional for
    # microtones: 60.5 is a quarter tone above middle C.
    pitch: float


def frequency(pitch: float) -> float:
    return A4_FREQUENCY * 2 ** ((pitch - A4_PITCH) / 12)


def _tone(pitch: float, length: float, sample_rate: int) -> np.ndarray:
    """A note `length` seconds long, plus its release."""
    count = int(round((length + RELEASE) * sample_rate))
    t = np.arange(count, dtype=np.float64) / sample_rate
    base = frequency(pitch)
    wave = np.zeros(count)
    for number, amplitude in enumerate(PARTIALS, start=1):
        # Partials past what the sample rate can carry would alias.
        if base * number >= sample_rate / 2:
            break
        wave += amplitude * np.sin(2 * np.pi * base * number * t)
    envelope = SUSTAIN + (1 - SUSTAIN) * np.exp(-DECAY_RATE * t)
    envelope *= np.clip(t / ATTACK, 0, 1)
    envelope *= np.clip((length + RELEASE - t) / RELEASE, 0, 1)
    return wave * envelope


def render(
    notes: Iterable[SynthNote], duration: float, sample_rate: int = SAMPLE_RATE
) -> np.ndarray:
    """The notes as mono audio, `duration` seconds long. A note past the end
    is cut there. The loudest moment is scaled to `PEAK`."""
    out = np.zeros(int(round(duration * sample_rate)))
    for note in notes:
        start = int(round(note.start * sample_rate))
        if note.end <= note.start or start >= len(out):
            continue
        tone = _tone(note.pitch, note.end - note.start, sample_rate)
        tone = tone[: len(out) - start]
        out[start : start + len(tone)] += tone
    if (loudest := np.abs(out).max(initial=0)) > 0:
        out *= PEAK / loudest
    return out.astype(np.float32)


def score_notes(notes: Iterable[Note]) -> list[SynthNote]:
    """What a score timeline's notes sound like: their sounding pitches, with
    tied notes joined into one. Unpitched notes are left out."""
    joins_next = (Note.TieType.START, Note.TieType.START_STOP)
    result: list[SynthNote] = []
    # A tie, still open, by staff and pitch: its index in `result`.
    open_ties: dict[tuple[int, float], int] = {}
    for note in sorted(notes):
        if not note.is_pitched:
            continue
        pitch = note.sounding_midi_pitch
        key = (note.staff_index, pitch)
        index = open_ties.pop(key, None)
        if index is not None and abs(result[index].end - note.start) < 1e-6:
            result[index] = SynthNote(result[index].start, note.end, pitch)
        else:
            index = len(result)
            result.append(SynthNote(note.start, note.end, pitch))
        if note.tie_type in joins_next:
            open_ties[key] = index
    return result


def get_score_notes() -> list[SynthNote]:
    """What all the score timelines sound like together."""
    result: list[SynthNote] = []
    for timeline in get(Get.TIMELINE_COLLECTION).get_timelines_by_type(ScoreTimeline):
        result += score_notes(
            c
            for c in timeline.component_manager.get_components()
            if c.KIND == ComponentKind.NOTE
        )
    return result


def to_wav(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> bytes:
    file = io.BytesIO()
    soundfile.write(file, samples, sample_rate, format="WAV", subtype="PCM_16")
    return file.getvalue()
