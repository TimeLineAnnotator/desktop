from pathlib import Path
from typing import Any

from tilia.parsers.csv.base import (
    TiliaCSVReader,
    get_column_not_found_error_message,
    get_params_indices,
)
from tilia.timelines.beat.measures import get_extension_from_beat_pattern
from tilia.timelines.beat.pattern import format_bars
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind


def beats_from_csv(
    timeline: BeatTimeline,
    path: Path,
    file_kwargs: dict[str, Any] | None = None,
    reader_kwargs: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """
    Create beat in a timeline from times extracted from a csv file.
    Assumes the first row of the file will contain headers.
    At least 'time' should be present.
    'measure' and 'is_first_in_measure' are optional.
    'time_signature' is optional and only needs filling where the time
    signature changes: it applies to the measures from its row's up to
    the next row that gives one, each over its own taps. A later row in
    the same measure replaces an earlier one. It is written as in the
    beat pattern, e.g. '6/8', or '4/4(3/2 3/2 1)' with taps.
    Returns a boolean indicating if the process was successful and
    an array with descriptions of any errors during the process.

    Please ensure 'time' column is sorted (ascending) before input.
    """

    errors = []
    measure_marks = None
    params = ["is_first_in_measure", "measure", "time"]
    optional_params = ["is_first_in_measure", "measure"]
    parsers = [str, int, float]
    params_to_indices = []

    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        params_to_indices = get_params_indices(params, next(reader))

        if "time" not in params_to_indices:
            return False, [get_column_not_found_error_message("time")]
        if any(param in params_to_indices for param in optional_params):
            if "is_first_in_measure" in params_to_indices:
                is_reading_beats = True
            else:
                is_reading_beats = False
                beats_per_measure = timeline.beat_pattern_bars
                current_bpm_index = 0

            current_beat = 0
            current_measure = 1
            current_time = 0.0
            beats_in_measure = []
            measure_numbers = []
            measures_to_force_display = []

            def check_params() -> bool:
                for param, parser in zip(params, parsers, strict=True):
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
                    return False, errors

                if float(row[params_to_indices.get("time")]) < current_time:
                    errors.append(
                        "Time is not sorted in ascending order. Please sort before importing."
                    )
                    return False, errors
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
                    params_to_indices.get("measure")
                    and row[params_to_indices["measure"]] != ""
                    and (
                        # measure numbers are considered if is_first_in_measure is true
                        # or if is_first_in_measure is not present
                        not params_to_indices.get("is_first_in_measure")
                        or row[params_to_indices["is_first_in_measure"]].lower()
                        == "true"
                    )
                ):
                    current_measure = int(row[params_to_indices["measure"]])
                    # Every beat of a measure may carry its number.
                    if len(measure_numbers) not in measures_to_force_display:
                        measures_to_force_display.append(len(measure_numbers))

            beats_in_measure.append(current_beat)
            measure_numbers.append(current_measure)
            timeline.set_data("beat_pattern", format_bars(beats_in_measure))
            measure_marks = _get_measure_marks(
                beats_in_measure, measure_numbers, measures_to_force_display
            )

    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        time_signature_index = get_params_indices(["time_signature"], next(reader)).get(
            "time_signature"
        )
        rows = [row for row in reader if row]

    if measure_marks is None:
        # Times alone may come in any order. The beats follow their times,
        # so the measures the pattern makes of them, and the time signatures
        # given for those, must too.
        rows.sort(key=lambda row: float(row[params_to_indices["time"]]))
        counts = get_extension_from_beat_pattern(timeline.beat_pattern_bars, len(rows))
        measure_marks = _get_measure_marks(counts, list(range(1, len(counts) + 1)), [])

    created = []
    with timeline.component_manager.bulk():
        for row_index, row in enumerate(rows):
            override, always_shown = measure_marks.get(row_index, (None, False))
            component, fail_reason = timeline.create_component(
                ComponentKind.BEAT,
                time=float(row[params_to_indices["time"]]),
                is_first_in_measure=row_index in measure_marks,
                measure_number_override=override,
                measure_number_always_shown=always_shown,
            )
            if component:
                created.append((component, row))
            else:
                errors.append(fail_reason)
        # The time signatures the beat pattern gives, if any. A row's own,
        # below, replaces the one of its measure.
        timeline.lay_planned_beat_units(0)
    # Gives the first beat its default time signature, which a row of the
    # file can then replace.
    timeline.refresh_measures()

    if time_signature_index is None:
        return True, errors

    changes: list[tuple[int, str, list[str]]] = []
    for component, row in created:
        if time_signature_index >= len(row) or not row[time_signature_index].strip():
            continue
        measure_index, _ = timeline.get_measure_index(
            timeline.get_beat_index(component)
        )
        change = (measure_index, row[time_signature_index].strip(), row)
        if changes and changes[-1][0] == measure_index:
            changes[-1] = change
        else:
            changes.append(change)

    # The time signatures are drawn once, when the measures are refreshed.
    with timeline.component_manager.bulk():
        for index, (measure_index, text, row) in enumerate(changes):
            if index + 1 < len(changes):
                stop = changes[index + 1][0]
            else:
                stop = timeline.measure_count
            error = timeline.set_time_signature(text, measure_index, stop)
            if error:
                errors.append(f"{row}: '{text}' is not a valid time signature. {error}")
    timeline.refresh_measures()

    return True, errors


def _get_measure_marks(
    beats_in_measure: list[int],
    measure_numbers: list[int],
    measures_to_force_display: list[int],
) -> dict[int, tuple[int | None, bool]]:
    """
    The rows that start measures, with the number each of them gets where it
    isn't the previous measure's plus one, and whether it is always shown.
    """
    marks = {}
    row_index = 0
    for measure_index, count in enumerate(beats_in_measure):
        number = measure_numbers[measure_index]
        expected = measure_numbers[measure_index - 1] + 1 if measure_index else 1
        marks[row_index] = (
            None if number == expected else number,
            measure_index in measures_to_force_display,
        )
        row_index += count
    return marks
