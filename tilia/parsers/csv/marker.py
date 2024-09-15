from pathlib import Path
from typing import Optional, Any

from tilia.parsers.csv.base import (
    TiliaCSVReader,
    get_params_indices,
    display_column_not_found_error,
)
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.marker.timeline import MarkerTimeline


def import_by_time(
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
    Returns an array with descriptions of any issues during creation.
    """

    errors = []

    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        params_to_indices = get_params_indices(
            ["time", "label", "comments"], next(reader)
        )

        if "time" not in params_to_indices:
            display_column_not_found_error("time")
            return errors

        for row in reader:
            if not row:
                continue
            # validate time
            index = params_to_indices["time"]
            time_value = row[index]
            try:
                float(time_value)
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

            component, reason = timeline.create_component(
                ComponentKind.MARKER, **constructor_kwargs
            )

            if not component:
                errors.append(reason)

        return errors


def import_by_measure(
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
    Returns an array with any errors during the process.
    """

    errors = []
    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        params_to_indices = get_params_indices(
            ["measure", "fraction", "label", "comments"], next(reader)
        )

        if "measure" not in params_to_indices:
            display_column_not_found_error("measure")
            return errors

        for row in reader:
            if not row:
                continue
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
                        f"{measure_value=} | {fraction_value} "
                        f"is not a fraction value. Using 0 as a backup."
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
                marker, fail_reason = marker_tl.create_component(
                    ComponentKind.MARKER, time=time, **constructor_kwargs
                )
                if not marker:
                    errors.append(f"{measure=} | {fail_reason}")

        return errors
