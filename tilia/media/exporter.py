from pathlib import Path

import soundfile

import tilia.errors
from tilia.requests import LongOperation, Post, post
from tilia.ui.background_task import run_in_background


def _read_and_write_audio_segment(
    source_path: Path | str,
    destination_path: Path,
    start_time: float,
    end_time: float,
) -> None:
    """Runs on a worker thread -- must not call post()/get() or touch Qt."""
    if isinstance(source_path, Path):
        source_path = source_path.resolve()

    array, sample_rate = soundfile.read(source_path)
    requested_section = array[
        int(start_time * sample_rate) : int(end_time * sample_rate)
    ]

    soundfile.write(destination_path, requested_section, sample_rate)


def export_audio(
    source_path: Path | str,
    destination_path: Path,
    start_time: float,
    end_time: float,
) -> None:
    post(Post.LONG_OPERATION, LongOperation.STARTED, "Exporting audio...")

    def on_done(_result: object) -> None:
        post(Post.LONG_OPERATION, LongOperation.DONE)

    def on_error(exc: Exception) -> None:
        post(Post.LONG_OPERATION, LongOperation.DONE)
        tilia.errors.display(tilia.errors.EXPORT_AUDIO_FAILED, str(exc))

    run_in_background(
        lambda: _read_and_write_audio_segment(
            source_path, destination_path, start_time, end_time
        ),
        on_done=on_done,
        on_error=on_error,
    )
