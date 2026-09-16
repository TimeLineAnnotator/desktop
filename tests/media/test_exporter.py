import time

import numpy as np
import soundfile

from tests.utils import long_operation_spy, wait_until
from tilia.media.exporter import export_audio
from tilia.requests import LongOperation


def _write_wav(path, duration_seconds=2.0, sample_rate=44100):
    t = np.linspace(0, duration_seconds, int(duration_seconds * sample_rate))
    data = np.sin(2 * np.pi * 440 * t)
    soundfile.write(path, data, sample_rate)
    return sample_rate


def _read_with_retry(path, attempts=10, delay=0.05):
    """Windows can hold a brief scan lock (AV/indexer minifilter) on a file
    even after the writer's own close() has returned, so an immediate
    reopen from another thread can hit a sharing violation."""
    for attempt in range(attempts):
        try:
            return soundfile.read(path)
        except soundfile.LibsndfileError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
    raise AssertionError("unreachable: attempts >= 1 always returns or raises above")


class TestExportAudio:
    def test_writes_requested_segment(self, tmp_path, tilia_errors):
        source = tmp_path / "source.wav"
        sample_rate = _write_wav(source)
        destination = tmp_path / "out.wav"

        with long_operation_spy() as calls:
            export_audio(source, destination, start_time=0.5, end_time=1.5)
            wait_until(lambda: any(phase == LongOperation.DONE for phase, _ in calls))

        # DONE fires on both the success and error paths (see export_audio's
        # on_error), so it alone doesn't prove the write succeeded. Assert
        # that explicitly so a real write failure surfaces here instead.
        assert not tilia_errors.errors, f"export_audio reported: {tilia_errors.errors}"
        assert destination.exists(), "destination file was never created"

        written, written_sample_rate = _read_with_retry(destination)
        assert written_sample_rate == sample_rate
        # Allow a couple of samples of slack from float rounding in the slice.
        assert abs(len(written) - sample_rate) <= 2

    def test_reports_progress_via_long_operation(self, tmp_path):
        source = tmp_path / "source.wav"
        _write_wav(source)
        destination = tmp_path / "out.wav"

        with long_operation_spy() as calls:
            export_audio(source, destination, start_time=0, end_time=1)
            wait_until(lambda: destination.exists())
            # DONE is posted from the GUI-thread completion callback, which
            # only runs once the queued connection is delivered -- keep
            # pumping past the file-exists check until it arrives.
            wait_until(lambda: any(phase == LongOperation.DONE for phase, _ in calls))

        phases = [phase for phase, _ in calls]
        assert phases[0] == LongOperation.STARTED
        assert LongOperation.DONE in phases

    def test_source_load_failure_displays_error(self, tmp_path, tilia_errors):
        source = tmp_path / "does_not_exist.wav"
        destination = tmp_path / "out.wav"

        export_audio(source, destination, start_time=0, end_time=1)
        wait_until(lambda: tilia_errors.errors)

        tilia_errors.assert_in_error_title("Export Audio")
