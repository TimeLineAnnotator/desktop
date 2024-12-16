from pathlib import Path
from typing import Any
from unittest.mock import patch, mock_open

import tilia.parsers.csv.pdf
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.pdf.timeline import PdfTimeline


def setup_beat_tl(beat_tl, beat_count: int):
    beat_tl.set_data("beat_pattern", [1])

    for i in range(beat_count):
        beat_tl.create_beat(i)


def _get_csv_data(*rows: list[Any]):
    return "\n".join([",".join(map(str, row)) for row in rows])


def call_patched_import_by_time_func(timeline: PdfTimeline, data: str):
    with patch("builtins.open", mock_open(read_data=data)):
        success, errors = tilia.parsers.csv.pdf.import_by_time(
            timeline,
            Path(),  # any path will do, as builtins.open is patched
        )
    return success, errors


def call_patched_import_by_measure_func(
    timeline: PdfTimeline, beat_tl: BeatTimeline, data: str
):
    with patch("builtins.open", mock_open(read_data=data)):
        success, errors = tilia.parsers.csv.pdf.import_by_measure(
            timeline,
            beat_tl,
            Path(),  # any path will do, as builtins.open is patched
        )
    return success, errors


class TestByTime:
    def test_pdf_marker_by_time(self, beat_tl, pdf_tl):
        pdf_tl.page_total = 1
        data = _get_csv_data(
            ["time", "page_number"],
            [5, 1],
        )

        success, errors = call_patched_import_by_time_func(pdf_tl, data)

        assert not errors
        assert len(pdf_tl) == 1

        pdf_marker = pdf_tl[0]

        assert pdf_marker.get_data("time") == 5
        assert pdf_marker.get_data("page_number") == 1

    def test_pdf_marker_by_time_multiple(self, beat_tl, pdf_tl):
        pdf_tl.page_total = 12
        rows = [["time", "page_number"], [0, 1], [1, 2], [10, 11], [11, 12], [20, 3]]

        data = _get_csv_data(*rows)

        success, errors = call_patched_import_by_time_func(pdf_tl, data)

        assert not errors
        for i, (time, page_number) in enumerate(rows[1:]):
            assert pdf_tl[i].get_data("time") == time
            assert pdf_tl[i].get_data("page_number") == page_number

    def test_invalid_values_return_errors(self, beat_tl, pdf_tl):
        pdf_tl.page_total = 1
        data = _get_csv_data(["time", "page_number"], ["invalid", 1], [1, "invalid"])

        success, errors = call_patched_import_by_time_func(pdf_tl, data)

        assert len(errors) == 2

    def test_time_out_of_bound_returns_error(self, beat_tl, pdf_tl):
        pdf_tl.page_total = 1

        data = _get_csv_data(["time", "page_number"], [0, -1], [1, 2])

        success, errors = call_patched_import_by_time_func(pdf_tl, data)

        assert len(errors) == 2
        assert pdf_tl.is_empty

    def test_valid_markers_get_created_even_if_errors_happen(self, beat_tl, pdf_tl):
        pdf_tl.page_total = 1

        data = _get_csv_data(
            ["time", "page_number"],
            [0, -1],
            [1, 1],
        )

        success, errors = call_patched_import_by_time_func(pdf_tl, data)

        assert len(errors) == 1
        assert len(pdf_tl) == 1
        assert pdf_tl[0].get_data("time") == 1
        assert pdf_tl[0].get_data("page_number") == 1


class TestByMeasure:
    def test_pdf_marker_by_measure(self, beat_tl, pdf_tl):
        pdf_tl.page_total = 1
        setup_beat_tl(beat_tl, 2)

        data = _get_csv_data(
            ["measure", "fraction", "page_number"],
            [1, 0, 1],
        )

        success, errors = call_patched_import_by_measure_func(pdf_tl, beat_tl, data)

        assert not errors
        assert len(pdf_tl) == 1
        assert pdf_tl[0].get_data("time") == 0

    def test_pdf_marker_by_measure_multiple(self, beat_tl, pdf_tl):
        pdf_tl.page_total = 5
        setup_beat_tl(beat_tl, 6)
        rows = [
            ["measure", "fraction", "page_number"],
            [1, 0, 1],
            [2, 0.1, 2],
            [3, 0.2, 3],
            [4, 0.3, 4],
            [5, 0.4, 5],
        ]

        data = _get_csv_data(*rows)

        success, errors = call_patched_import_by_measure_func(pdf_tl, beat_tl, data)

        assert not errors

        for i, (measure, fraction, page_number) in enumerate(rows[1:]):
            assert pdf_tl[i].get_data('time') == measure - 1 + fraction
            assert pdf_tl[i].get_data('page_number') == page_number

    def test_invalid_values_return_errors(self, beat_tl, pdf_tl):
        pdf_tl.page_total = 1
        setup_beat_tl(beat_tl, 2)
        data = _get_csv_data(
            ["measure", "fraction", "page_number"], ["invalid", 0, 1], [1, "invalid", 1], [1, 0, 'invalid']
        )

        success, errors = call_patched_import_by_measure_func(pdf_tl, beat_tl, data)

        assert len(errors) == 3

    def test_measure_out_of_bound_returns_error(self, beat_tl, pdf_tl):
        pdf_tl.page_total = 1
        setup_beat_tl(beat_tl, 5)
        data = _get_csv_data(["measure", "fraction", "page_number"], [-1, 0, 1], [6, 0, 1])

        success, errors = call_patched_import_by_measure_func(pdf_tl, beat_tl, data)

        assert len(errors) == 2
        assert pdf_tl.is_empty

    def test_valid_markers_get_created_even_if_errors_happen(self, beat_tl, pdf_tl):
        pdf_tl.page_total = 1
        setup_beat_tl(beat_tl, 1)

        data = _get_csv_data(
            ["measure", "fraction", "page_number"],
            ['this', 'line', 'errors'],
            [1, 0, 1],
        )

        success, errors = call_patched_import_by_measure_func(pdf_tl, beat_tl, data)

        assert len(errors) == 1
        assert len(pdf_tl) == 1
        assert pdf_tl[0].get_data("time") == 0
        assert pdf_tl[0].get_data("page_number") == 1
