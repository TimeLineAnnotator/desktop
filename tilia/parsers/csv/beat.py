from pathlib import Path
from typing import Optional, Any

from tilia.parsers.csv.base import (
    TiliaCSVReader,
    get_params_indices,
    display_column_not_found_error,
)
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind


def beats_from_csv(
    timeline: BeatTimeline,
    path: Path,
    file_kwargs: Optional[dict[str, Any]] = None,
    reader_kwargs: Optional[dict[str, Any]] = None,
) -> list[str]:
    """
    Create beat in a timeline from times extracted from a csv file.
    Assumes the first row of the file will contain headers.
    At least 'time' should be present.
    'measure_number' and 'is_first_in_measure' are optional.
    Returns an array with descriptions of any CreateComponentErrors
    raised during beat creation.

    Please ensure 'time' column is sorted (ascending) before input.
    """

    errors = []
    params = ["is_first_in_measure", "measure_number", "time"]
    optional_params = ["is_first_in_measure", "measure_number"]
    parsers = [str, int, float]
    params_to_indices = []

    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        params_to_indices = get_params_indices(params, next(reader))

        if "time" not in params_to_indices:
            display_column_not_found_error("time")
            return errors

        if any(param in params_to_indices for param in optional_params):
            if "is_first_in_measure" in params_to_indices:
                is_reading_beats = True
                timeline.beat_pattern = []
            else:
                is_reading_beats = False
                beats_per_measure = timeline.beat_pattern
                current_bpm_index = 0

            current_beat = 0
            current_measure = 1
            current_time = 0.0
            beats_in_measure = []
            measure_numbers = []
            measures_to_force_display = []

            def check_params() -> bool:
                for param, parser in zip(params, parsers):
                    if param in params_to_indices:
                        try:
                            index = params_to_indices[param]
                            if row[index] != "" or param not in optional_params:
                                parser(row[index])
                                return True
                        except ValueError:
                            errors.append(
                                f"{row}'{row[index]}' is not a valid {param.replace('_', ' ')}"
                            )
                            return False

            for row in reader:
                if not row:
                    continue

                if not check_params():
                    return errors

                if float(row[params_to_indices.get("time")]) < current_time:
                    errors.append(
                        "Time is not sorted in ascending order. Please sort before importing."
                    )
                    return errors
                else:
                    current_time = float(row[params_to_indices.get("time")])

                if (
                    params_to_indices.get("is_first_in_measure")
                    and row[params_to_indices["is_first_in_measure"]].lower() == "true"
                    and current_beat != 0
                ) or (
                    not is_reading_beats
                    and current_beat >= beats_per_measure[current_bpm_index]
                ):
                    beats_in_measure.append(current_beat)
                    measure_numbers.append(current_measure)
                    current_beat = 1
                    current_measure += 1

                    if not is_reading_beats:
                        current_bpm_index = (current_bpm_index + 1) % len(
                            beats_per_measure
                        )

                else:
                    current_beat += 1

                if (
                    params_to_indices.get("measure_number")
                    and row[params_to_indices["measure_number"]] != ""
                    and (
                        # measure numbers are considered if is_first_in_measure is true
                        # or if is_first_in_measure is not present
                        not params_to_indices.get("is_first_in_measure")
                        or row[params_to_indices['is_first_in_measure']].lower() == 'true'
                    )
                ):
                    current_measure = int(row[params_to_indices["measure_number"]])
                    measures_to_force_display.append(len(measure_numbers))

            beats_in_measure.append(current_beat)
            measure_numbers.append(current_measure)
            timeline.set_data("beat_pattern", beats_in_measure)
            timeline.set_data("measure_numbers", measure_numbers)
            timeline.set_data("measures_to_force_display", measures_to_force_display)

    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        next(reader)
        for row in reader:
            if not row:
                continue

            constructor_kwargs = {}
            index = params_to_indices["time"]
            constructor_kwargs["time"] = float(row[index])

            component, fail_reason = timeline.create_component(
                ComponentKind.BEAT, **constructor_kwargs
            )
            if not component:
                errors.append(fail_reason)

            timeline.recalculate_measures()
        return errors
