from pathlib import Path

import csv
from typing import Any, Optional

from tilia.exceptions import CreateComponentError
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.marker.timeline import MarkerTimeline


class TiliaCSVReader:
    def __init__(
        self,
        path: Path,
        file_kwargs: Optional[dict[str, Any]] = None,
        reader_kwargs: Optional[dict[str, Any]] = None,
    ):
        self.path = path
        self.file_kwargs = file_kwargs or {}
        self.reader_kwargs = reader_kwargs or {}

    def __enter__(self):
        self.file = open(self.path, newline="", **self.file_kwargs)
        return csv.reader(self.file, **self.reader_kwargs)

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.file.close()


def get_params_indices(params: list[str], headers: list[str]) -> dict[str, int]:
    """
    Returns a dictionary with parameters in 'params' as keys and their first index in 'headers'
    as values. If the parameters is not found in 'headers', it is not included in the result.
    """

    result = {}

    for p in params:
        try:
            result[p] = headers.index(p)
        except ValueError:
            pass

    return result


def markers_by_time_from_csv(
    timeline: MarkerTimeline,
    path: Path,
    file_kwargs: Optional[dict[str, Any]] = None,
    reader_kwargs: Optional[dict[str, Any]] = None,
) -> list[str]:
    """
    Create markers in a timeline from a csv file with times.
    Assumes the first row of the file will contain headers.
    Header names should match marker properties. All properties
    but 'time' are optional.
    Returns an array with descriptions of any CreateComponentErrors
    raised during marker creation.
    """

    errors = []

    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        params_to_indices = get_params_indices(
            ["time", "label", "comments"], next(reader)
        )

        if "time" not in params_to_indices:
            raise ValueError("Column 'time' not found on first row of csv file.")

        for row in reader:
            # validate time
            index = params_to_indices["time"]
            time_value = row[index]
            try:
                time = int(time_value)
            except ValueError:
                errors.append(f"{time_value=} | {time_value} is not a valid time")
                continue

            params = ["time", "label", "comments"]
            parsers = [float, str, str]
            constructor_kwargs = {}

            for param, parser in zip(params, parsers):
                if param in params_to_indices:
                    index = params_to_indices[param]
                    constructor_kwargs[param] = parser(row[index])

            try:
                timeline.create_timeline_component(
                    ComponentKind.MARKER, **constructor_kwargs
                )
            except CreateComponentError as exc:
                time = params_to_indices["time"]
                errors.append(f"{time=} | {str(exc)}")

        return errors


def markers_by_measure_from_csv(
    marker_tl: MarkerTimeline,
    beat_tl: BeatTimeline,
    path: Path,
    file_kwargs: Optional[dict[str, Any]] = None,
    reader_kwargs: Optional[dict[str, Any]] = None,
) -> list[str]:
    """
    Create markers in a timeline from a csv file with 1-based measure indices.
    Assumes the first row of the file will contain headers.
    Header names should match marker propertiesAll properties
    but 'measure' are optional.
    Returns an array with descriptions of any CreateComponentErrors
    raised during marker creation.

    Note: The measure column should have measure indices, not measure numbers.
    That means that repeated measure numbers should not be taken into account.
    """

    errors = []
    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        params_to_indices = get_params_indices(
            ["measure", "fraction", "label", "comments"], next(reader)
        )

        if "measure" not in params_to_indices:
            raise ValueError("Column 'measure' not found on first row of csv file.")

        for row in reader:
            # get and validate measure
            measure_value = row[params_to_indices["measure"]]
            try:
                measure = int(measure_value)
            except ValueError:
                errors.append(
                    f"{measure_value=} | {measure_value} is not a valid measure number"
                )
                continue
            fraction = 0

            # get and validate fraction
            if "fraction" in params_to_indices:
                fraction_value = row[params_to_indices["fraction"]]
                try:
                    fraction = float(fraction_value)
                except ValueError:
                    errors.append(
                        f"{measure_value=} | {fraction_value} is not a fraction value. Using 0 as a backup."
                    )
                    fraction = 0

            times = beat_tl.get_time_by_measure(measure, fraction)

            if not times:
                errors.append(f"{measure=} | No measure with number {measure}")
                continue

            params = ["label", "comments"]
            parsers = [str, str]
            constructor_kwargs = {}

            for param, parser in zip(params, parsers):
                if param in params_to_indices:
                    index = params_to_indices[param]
                    constructor_kwargs[param] = parser(row[index])

            for time in times:
                try:
                    marker_tl.create_timeline_component(
                        ComponentKind.MARKER, time=time, **constructor_kwargs
                    )
                except CreateComponentError as exc:
                    errors.append(f"{measure=} | {str(exc)}")

        return errors
