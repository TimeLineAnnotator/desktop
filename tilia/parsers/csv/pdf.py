import functools
from pathlib import Path
from typing import Any

from tilia.parsers.csv.base import TiliaCSVReader
from tilia.parsers.csv.common import (
    _get_attrs_indices,
    _validate_required_attrs,
    _get_attr_data,
    _parse_attr_data,
    _parse_measure_fraction,
)
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.pdf.timeline import PdfTimeline


def _create_component(timeline, time, page_number):
    errors = []
    component, fail_reason = timeline.create_component(
        ComponentKind.PDF_MARKER, time, page_number
    )
    if not component:
        errors.append(fail_reason)

    return errors


def _validate_page_number(timeline: PdfTimeline, value: int):
    return 1 <= value <= timeline.page_total


def _parse_page_number(timeline: PdfTimeline, value: str):
    value = int(value)  # parse will fail if this raises a ValueError

    if not _validate_page_number(timeline, value):
        raise ValueError(f"APPEND:The PDF has no page with that number.")

    return value


def import_by_time(
    timeline: PdfTimeline,
    path: Path,
    file_kwargs: dict[str, Any] | None = None,
    reader_kwargs: dict[str, Any] | None = None,
) -> list[str]:
    """
    Create .pdf markers in a timeline from a csv file with times.
    Assumes the first row of the file will contain headers.
    Header names must contain 'time' and 'page_number'.
    Returns an array with descriptions of any errors during the process.
    """
    errors = []

    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        try:
            header = next(reader)
        except StopIteration:
            return ["Can't import: file is empty."]

        attrs_with_parsers = [
            ("time", float),
            ("page_number", functools.partial(_parse_page_number, timeline)),
        ]

        required_attrs = ["page_number", "time"]
        all_attrs = [x[0] for x in attrs_with_parsers]

        indices = _get_attrs_indices(all_attrs, header)

        success, error = _validate_required_attrs(required_attrs, header)
        if not success:
            errors.append(error)
            return errors

        attr_data = _get_attr_data(attrs_with_parsers, indices)

        for row_data in reader:
            if not row_data:
                continue

            success, row_errors, attr_to_value = _parse_attr_data(
                row_data, attr_data, required_attrs
            )
            errors += row_errors
            if not success:
                continue

            errors += _create_component(
                timeline, attr_to_value["time"], attr_to_value["page_number"]
            )

        return errors


def import_by_measure(
    pdf_tl: PdfTimeline,
    beat_tl: BeatTimeline,
    path: Path,
    file_kwargs: dict[str, Any] | None = None,
    reader_kwargs: dict[str, Any] | None = None,
) -> list[str]:
    """
    Create .pdf markers in a timeline from a csv file with 1-based measure indices.
    Assumes the first row of the file will contain headers.
    Header names must contain 'time' and 'page_number'.
    Returns an array with any errors during the process.
    """
    errors = []

    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        try:
            header = next(reader)
        except StopIteration:
            return ["Can't import: file is empty."]

        attrs_with_parsers = [
            ("measure", int),
            ("fraction", _parse_measure_fraction),
            ("page_number", functools.partial(_parse_page_number, pdf_tl)),
        ]

        required_attrs = ["measure", "page_number"]
        all_attrs = [x[0] for x in attrs_with_parsers]

        indices = _get_attrs_indices(all_attrs, header)

        success, error = _validate_required_attrs(required_attrs, header)
        if not success:
            errors.append(error)
            return errors

        attr_data = _get_attr_data(attrs_with_parsers, indices)

        for row_data in reader:
            if not row_data:
                continue

            success, row_errors, attr_to_value = _parse_attr_data(
                row_data, attr_data, required_attrs
            )
            errors += row_errors
            if not success:
                continue

            measure_n = attr_to_value["measure"]
            times = beat_tl.get_time_by_measure(
                measure_n, attr_to_value.get("fraction", 0)
            )

            if not times:
                errors.append(f"No measure with number {measure_n}")
                continue

            for time in times:
                errors += _create_component(pdf_tl, time, attr_to_value["page_number"])

        return errors
