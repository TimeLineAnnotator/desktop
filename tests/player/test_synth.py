import numpy as np
import pytest

from tilia.media.synth import PEAK, SAMPLE_RATE, SynthNote, frequency, render


def dominant_frequency(audio: np.ndarray) -> float:
    spectrum = np.abs(np.fft.rfft(audio * np.hanning(len(audio))))
    return np.fft.rfftfreq(len(audio), 1 / SAMPLE_RATE)[spectrum.argmax()]


class TestRender:
    def test_lasts_the_given_duration(self):
        audio = render([SynthNote(0, 1, 60)], 3.5)

        assert len(audio) == round(3.5 * SAMPLE_RATE)

    def test_sounds_at_the_note_pitch(self):
        audio = render([SynthNote(0, 2, 69)], 2)

        assert dominant_frequency(audio) == pytest.approx(440, abs=1)

    def test_quarter_tone_is_exact(self):
        # A quarter tone above A4: 440 * 2 ** (1 / 24).
        audio = render([SynthNote(0, 2, 69.5)], 2)

        assert dominant_frequency(audio) == pytest.approx(452.9, abs=1)
        assert frequency(69.5) == pytest.approx(452.89, abs=0.01)

    def test_silent_before_and_after_the_note(self):
        audio = render([SynthNote(1, 2, 60)], 4)

        assert not audio[: SAMPLE_RATE - 1].any()
        assert not audio[int(2.2 * SAMPLE_RATE) :].any()
        assert np.abs(audio[int(1.1 * SAMPLE_RATE) : 2 * SAMPLE_RATE]).max() > 0.1

    def test_loudest_moment_is_scaled_to_peak(self):
        chord = [SynthNote(0, 1, pitch) for pitch in (60, 64, 67, 71)]

        audio = render(chord, 1)

        assert np.abs(audio).max() == pytest.approx(PEAK, abs=1e-6)

    def test_note_past_the_end_is_cut(self):
        audio = render([SynthNote(0.5, 5, 60)], 1)

        assert len(audio) == SAMPLE_RATE
        assert np.abs(audio[-100:]).max() > 0

    def test_note_without_length_is_left_out(self):
        audio = render([SynthNote(1, 1, 60)], 2)

        assert not audio.any()
