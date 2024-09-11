from pathlib import Path
from unittest.mock import patch, mock_open

from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.pdf.timeline import PdfTimeline


def assert_in_errors(string: str, errors: list[str]):
    all_errors = "".join(errors)
    assert string in all_errors


def call_patched_import_by_time_func(timeline: PdfTimeline, data: str):
    with patch("builtins.open", mock_open(read_data=data)):
        errors = timeline.import_by_time(
            Path(),  # any path will do, as builtins.open is patched
        )
    return errors


def call_patched_import_by_measure_func(
    timeline: PdfTimeline, beat_tl: BeatTimeline, data: str
):
    with patch("builtins.open", mock_open(read_data=data)):
        errors = timeline.import_by_measure(
            beat_tl,
            Path(),  # any path will do, as builtins.open is patched
        )
    return errors
