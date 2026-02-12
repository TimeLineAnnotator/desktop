from pathlib import Path
from typing import Optional, Any

from tilia.parsers.csv.base import (
    TiliaCSVReader,
    get_params_indices,
    get_column_not_found_error_message,
)
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.hierarchy.timeline import HierarchyTimeline


def import_by_time(
    timeline: HierarchyTimeline,
    path: Path,
    file_kwargs: Optional[dict[str, Any]] = None,
    reader_kwargs: Optional[dict[str, Any]] = None,
) -> tuple[bool, list[str]]:
    """
    Create hierarchies in a timeline from a csv file with times.
    Assumes the first row of the file will contain headers.
    Header names should match hierarchy properties.
    At least, 'start', 'end' and 'level' should be present.
    Returns a boolean indicating if the process was successful and
    an array with descriptions of any errors during the process.
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
        parsers = [float, float, int, float, float, str, str, str, str, str]
        params_to_indices = get_params_indices(params, next(reader))

        for attr in ["start", "end", "level"]:
            if attr not in params_to_indices:
                return False, [get_column_not_found_error_message(attr)]
        for row in reader:
            if not row:
                continue
            constructor_args = {}
            for i, attr in enumerate(["start", "end", "level"]):
                index = params_to_indices[attr]
                value = row[index]

                try:
                    constructor_args[attr] = parsers[i](value)
                except ValueError:
                    errors.append(f"'{value}' is not a valid {attr.replace('_', ' ')}")
                    continue

            for param, parser in zip(params, parsers, strict=True):
                if param in params_to_indices:
                    index = params_to_indices[param]
                    constructor_args[param] = parser(row[index])

            component, fail_reason = timeline.create_component(
                ComponentKind.HIERARCHY, **constructor_args
            )
            if not component:
                errors.append(fail_reason)

        return True, errors


def import_by_measure(
    hierarchy_tl: HierarchyTimeline,
    beat_tl: BeatTimeline,
    path: Path,
    file_kwargs: Optional[dict[str, Any]] = None,
    reader_kwargs: Optional[dict[str, Any]] = None,
) -> tuple[bool, list[str]]:
    """
    Create hierarchies in a timeline from a csv file with 1-based measure indices.
    Assumes the first row of the file will contain headers.
    Header names should match hierarchy propertiesAll properties
    but 'measure' are optional.
    Returns a boolean indicating if the process was successful and
    an array with descriptions of any errors during the process.

    Note: The measure column should have measure indices, not measure numbers.
    That means that repeated measure numbers should not be taken into account.
    """

    errors = []

    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        header = next(reader)

        required_params = [
            ("start", int),
            ("end", int),
            ("level", int),
        ]

        optional_params = [
            ("start_fraction", float),
            ("end_fraction", float),
            ("pre_start", float),
            ("pre_start_fraction", float),
            ("post_end", float),
            ("post_end_fraction", float),
            ("label", str),
            ("color", str),
            ("comments", str),
            ("formal_type", str),
            ("formal_function", str),
        ]

        params_to_indices = get_params_indices([p[0] for p in required_params], header)
        params_to_indices.update(
            get_params_indices([p[0] for p in optional_params], header)
        )

        for attr, _ in required_params:
            if attr not in params_to_indices:
                return False, [get_column_not_found_error_message(attr)]
        for row in reader:
            if not row:
                continue
            required_values = {}
            try:
                for attr, parser in required_params:
                    index = params_to_indices[attr]
                    value = row[index]
                    required_values[attr] = parser(value)
            except ValueError:
                errors.append(f"'{value}' is not a valid {attr.replace('_', ' ')}")
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
                            f"start={required_values['start']}, "
                            f"end={required_values['end']} | "
                            f"{fraction_value} is not a fraction value. "
                            "Defaulting to 0."
                        )
                        fractions[ext] = 0

            times = {"start": [0], "end": [0]}

            # get and validate times
            for ext in times:
                times[ext] = beat_tl.get_time_by_measure(
                    required_values[ext], fractions[ext], ext == "end"
                )
                if not times[ext]:
                    value = required_values[ext]
                    errors.append(f"'{ext}={value} | No measure with number {value}")
                    continue

            # get remaining params
            kwargs = {}
            remaining_params = [
                p
                for p in optional_params
                if p[0] not in ["start_fraction", "end_fraction"]
            ]
            for param, parser in remaining_params:
                if param in params_to_indices:
                    index = params_to_indices[param]
                    try:
                        kwargs[param] = parser(row[index])
                    except ValueError:
                        errors.append(
                            f"'start'={required_values['start']}, "
                            f"end={required_values['end']} | '{row[index]}' "
                            f"is not a valid {param} value."
                        )

            # create hierarchies
            start_times = times["start"].copy()
            end_times = times["end"].copy()
            # start_times and end_times are always sorted. If start_times[n] is greater than end_time[n], all start_times[n+] will also be greater than end_times[n], which would create a segment-like component with start > end. Therefore, pop off head of end_times until a suitable end_time is found.
            while len(start_times) and len(end_times):
                if (start := start_times[0]) < (end := end_times[0]):
                    component, fail_reason = hierarchy_tl.create_component(
                        ComponentKind.HIERARCHY,
                        start,
                        end,
                        required_values["level"],
                        start_fraction=fractions["start"],
                        end_fraction=fractions["end"],
                        **kwargs,
                    )
                    if not component:
                        errors.append(fail_reason)
                    start_times.pop(0)
                    end_times.pop(0)
                    continue
                while len(end_times) and start_times[0] > end_times[0]:
                    end_times.pop(0)

        return True, errors
