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
    Assumes the first row of the file will contain a header named 'time'.
    Returns an array with descriptions of any errors during the process.
    """

    errors = []

    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        params_to_indices = get_params_indices(["time"], next(reader))

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
                int(time_value)
            except ValueError:
                errors.append(f"{time_value=} | {time_value} is not a valid time")
                continue

            params = ["time"]
            parsers = [float]
            constructor_kwargs = {}

            for param, parser in zip(params, parsers):
                if param in params_to_indices:
                    index = params_to_indices[param]
                    constructor_kwargs[param] = parser(row[index])

            component, fail_reason = timeline.create_timeline_component(
                ComponentKind.BEAT, **constructor_kwargs
            )
            if not component:
                errors.append(fail_reason)

            timeline.recalculate_measures()
        return errors
