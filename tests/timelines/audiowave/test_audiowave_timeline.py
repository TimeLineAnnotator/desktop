import numpy as np
import soundfile

from tests.utils import long_operation_spy, wait_until
from tilia.requests import LongOperation, Post, post
from tilia.timelines.audiowave.timeline import AudioWaveTimeline


def _write_wav(path, duration_seconds=1.0, sample_rate=44100):
    t = np.linspace(0, duration_seconds, int(duration_seconds * sample_rate))
    data = np.sin(2 * np.pi * 440 * t)
    soundfile.write(path, data, sample_rate)


class TestAudioWaveTimelineRefresh:
    def test_creates_amplitude_bars_from_real_audio(self, qtui, tls, tmp_path):
        wav_path = tmp_path / "audio.wav"
        _write_wav(wav_path)
        post(Post.APP_MEDIA_LOAD, str(wav_path))

        tl = tls.create_timeline(AudioWaveTimeline)

        wait_until(lambda: len(tl.components) > 0)

        amplitudes = sorted(tl.components)
        assert len(amplitudes) > 0
        assert all(0 <= a.get_data("amplitude") <= 1 for a in amplitudes)

    def test_reports_progress_via_long_operation(self, qtui, tls, tmp_path):
        wav_path = tmp_path / "audio.wav"
        _write_wav(wav_path)
        post(Post.APP_MEDIA_LOAD, str(wav_path))

        with long_operation_spy() as calls:
            tl = tls.create_timeline(AudioWaveTimeline)
            wait_until(lambda: len(tl.components) > 0)
            wait_until(lambda: any(phase == LongOperation.DONE for phase, _ in calls))

        phases = [phase for phase, _ in calls]
        assert phases[0] == LongOperation.STARTED
        assert LongOperation.PROGRESS in phases
        assert LongOperation.DONE in phases
