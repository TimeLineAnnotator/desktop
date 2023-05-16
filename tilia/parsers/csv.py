from pathlib import Path

import csv
from typing import Any, Optional

from tilia.exceptions import CreateComponentError
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
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


def hierarchies_by_time_from_csv(
    timeline: HierarchyTimeline,
    path: Path,
    file_kwargs: Optional[dict[str, Any]] = None,
    reader_kwargs: Optional[dict[str, Any]] = None,
) -> list[str]:
    """
    Create hierarchies in a timeline from a csv file with times.
    Assumes the first row of the file will contain headers.
    Header names should match hierarchy properties.
    At least, 'start', 'end' and 'level' should be present.
    Returns an array with descriptions of any CreateComponentErrors
    raised during creation.
    """

    errors = []

    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        params = [
            "start",
            "end",
            "level",
            "pre_start",
            "post_end",
            "label",
            "color",
            "comments",
            "formal_type",
            "formal_function",
        ]
        parsers = [float, float, int, float, float, str, str, str]
        params_to_indices = get_params_indices(params, next(reader))

        for attr in ["start", "end", "level"]:
            if attr not in params_to_indices:
                raise ValueError(f"Column '{attr}' not found on first row of csv file.")

        for row in reader:
            constructor_args = {}
            for i, attr in enumerate(["start", "end", "level"]):
                index = params_to_indices[attr]
                value = row[index]

                try:
                    constructor_args[attr] = parsers[i](value)
                except ValueError:
                    errors.append(f"{value=} | {value} is not a valid {attr}")
                    continue

            for param, parser in zip(params, parsers):
                if param in params_to_indices:
                    index = params_to_indices[param]
                    constructor_args[param] = parser(row[index])

            try:
                timeline.create_timeline_component(
                    ComponentKind.HIERARCHY, **constructor_args
                )
            except CreateComponentError as exc:
                start = params_to_indices["start"]
                end = params_to_indices["end"]
                level = params_to_indices["level"]

                errors.append(f"{start=}, {end=}, {level=} | {str(exc)}")

        return errors


def hierarchies_by_measure_from_csv(
    hierarchy_tl: HierarchyTimeline,
    beat_tl: BeatTimeline,
    path: Path,
    file_kwargs: Optional[dict[str, Any]] = None,
    reader_kwargs: Optional[dict[str, Any]] = None,
) -> list[str]:
    """
    Create hierarchies in a timeline from a csv file with 1-based measure indices.
    Assumes the first row of the file will contain headers.
    Header names should match hierarchy propertiesAll properties
    but 'measure' are optional.
    Returns an array with descriptions of any CreateComponentErrors
    raised during hierarchy creation.

    Note: The measure column should have measure indices, not measure numbers.
    That means that repeated measure numbers should not be taken into account.
    """

    errors = []

    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        header = next(reader)

        required_params = [
            (
                "start",
                float,
            ),
            (
                "end",
                float,
            ),
            ("level", int),
        ]

        optional_params = [
            (
                "start_fraction",
                float,
            ),
            (
                "end_fraction",
                float,
            ),
            (
                "pre_start",
                float,
            ),
            (
                "pre_start_fraction",
                float,
            ),
            (
                "post_end",
                float,
            ),
            (
                "post_end_fraction",
                float,
            ),
            (
                "label",
                str,
            ),
            (
                "color",
                str,
            ),
            (
                "comments",
                str,
            ),
            (
                "formal_type",
                str,
            ),
            (
                "formal_function",
                str,
            ),
        ]

        params_to_indices = get_params_indices([p[0] for p in required_params], header)
        params_to_indices.update(
            get_params_indices([p[0] for p in optional_params], header)
        )

        for attr, _ in required_params:
            if attr not in params_to_indices:
                raise ValueError(f"Column '{attr}' not found on first row of csv file.")

        for row in reader:
            required_values = {}
            try:
                for attr, parser in required_params:
                    index = params_to_indices[attr]
                    value = row[index]
                    required_values[attr] = parser(value)
            except ValueError:
                errors.append(f"{value=} | {value} is not a valid {attr}")
                continue

            # get and validate fraction
            fractions = {"start": 0, "end": 0}

            for ext in fractions:
                attr = ext + "_fraction"
                if attr in params_to_indices:
                    fraction_value = row[params_to_indices[attr]]
                    try:
                        fractions[ext] = float(fraction_value)
                    except ValueError:
                        errors.append(
                            f"start={required_values['start']}, end={required_values['end']} | {fraction_value} is not a fraction value. Defaulting to 0."
                        )
                        fractions[ext] = 0

            times = {"start": 0, "end": 0}

            # get and validate times
            for ext in times:
                times[ext] = beat_tl.get_time_by_measure(
                    required_values[ext], fractions[ext]
                )
                if not times[ext]:
                    value = required_values[ext]
                    errors.append(f"'{ext}={value} | No measure with number {value}")
                    continue

            # get remaining params
            kwargs = {}
            reamining_params = [
                p
                for p in optional_params
                if p[0] not in ["start_fraction", "end_fraction"]
            ]
            for param, parser in reamining_params:
                if param in params_to_indices:
                    index = params_to_indices[param]
                    try:
                        kwargs[param] = parser(row[index])
                    except ValueError:
                        errors.append(
                            f"'start'={required_values['start']}, end={required_values['end']} | '{row[index]}' is not a valid {param} value."
                        )

            # create hierarchies
            for start, end in zip(times["start"], times["end"]):
                try:
                    hierarchy_tl.create_timeline_component(
                        ComponentKind.HIERARCHY,
                        start,
                        end,
                        required_values["level"],
                        start_fraction=fractions["start"],
                        end_fraction=fractions["end"],
                        **kwargs,
                    )
                except CreateComponentError as exc:
                    errors.append(f"{start=}, {end=} | {str(exc)}")

        return errors
