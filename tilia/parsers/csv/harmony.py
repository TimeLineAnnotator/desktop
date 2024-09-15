from pathlib import Path
from typing import Any, Optional, Literal

import music21

import tilia.timelines.harmony.constants
from tilia.parsers.csv.common import (
    _get_attrs_indices,
    _validate_required_attrs,
    _parse_attr_data,
    _get_attr_data,
    _parse_measure_fraction,
)
from tilia.parsers.csv.base import TiliaCSVReader
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.harmony.timeline import HarmonyTimeline
from tilia.timelines.harmony.components.harmony import (
    get_params_from_text as get_harmony_params_from_text,
)
from tilia.timelines.harmony.components.mode import (
    get_params_from_text as get_mode_params_from_text,
)


def _parse_display_mode(value: str):
    valid_modes = tilia.timelines.harmony.constants.HARMONY_DISPLAY_MODES
    if value in valid_modes:
        return value
    else:
        raise ValueError(f"APPEND:Must be one of {valid_modes}")


def _parse_custom_text_font_type(value: str):
    valid_types = tilia.timelines.harmony.constants.FONT_TYPES
    if value in valid_types:
        return value
    else:
        raise ValueError(f"APPEND:Must be one of {valid_types}")


def _parse_harmony_or_key(value: str):
    if value in ["harmony", "key"]:
        return value
    else:
        raise ValueError('APPEND:Must be "harmony" or "key".')


def _get_component_params_from_text(
    component_kind: Literal["harmony", "key"], text: str, key: music21.key.Key
):
    if component_kind == "harmony":
        success, params = get_harmony_params_from_text(text, key)
    else:
        success, params = get_mode_params_from_text(text)

    return success, params


HARMONY_INVALID_SYMBOL_ERROR = '"{} is not a valid symbol for a harmony. Must be a chord symbol or a roman numeral."'
MODE_INVALID_SYMBOL_ERROR = '"{} is not a valid symbol for a key."'


def _get_invalid_symbol_error(component_kind: Literal["harmony", "key"], symbol: str):
    return (
        HARMONY_INVALID_SYMBOL_ERROR.format(symbol)
        if component_kind == "harmony"
        else MODE_INVALID_SYMBOL_ERROR.format(symbol)
    )


def _create_component(component_kind, symbol, harmony_tl, time):
    errors = []
    success, params = _get_component_params_from_text(
        component_kind, symbol, harmony_tl.get_key_by_time(time)
    )

    if not success:
        errors.append(_get_invalid_symbol_error(component_kind, symbol))
        return errors

    component, fail_reason = harmony_tl.create_component(
        (ComponentKind.HARMONY if component_kind == "harmony" else ComponentKind.MODE),
        time,
        **params,
    )
    if not component:
        errors.append(fail_reason)

    return errors


def import_by_time(
    timeline: HarmonyTimeline,
    path: Path,
    file_kwargs: Optional[dict[str, Any]] = None,
    reader_kwargs: Optional[dict[str, Any]] = None,
) -> list[str]:
    """
    Create harmonies in a timeline from a csv file with times.
    Assumes the first row of the file will contain headers.
    Header names should match harmony properties.
    At least, 'harmony_or_key', 'time' and 'symbol' should be present.
    Returns an array with descriptions of any errors during the process.
    """
    errors = []

    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        try:
            header = next(reader)
        except StopIteration:
            return ["Can't import: file is empty."]

        attrs_with_parsers = [
            ("harmony_or_key", _parse_harmony_or_key),
            ("time", float),
            ("symbol", str),
            ("comments", str),
            ("display_mode", _parse_display_mode),
            ("custom_text", str),
            ("custom_text_font_type", _parse_custom_text_font_type),
        ]

        required_attrs = ["harmony_or_key", "time", "symbol"]
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
                attr_to_value["harmony_or_key"],
                attr_to_value["symbol"],
                timeline,
                attr_to_value["time"],
            )

        return errors


def import_by_measure(
    harmony_tl: HarmonyTimeline,
    beat_tl: BeatTimeline,
    path: Path,
    file_kwargs: Optional[dict[str, Any]] = None,
    reader_kwargs: Optional[dict[str, Any]] = None,
) -> list[str]:
    """
    Create harmonies in a timeline from a csv file with csv file with 1-based measure indices.
    Assumes the first row of the file will contain headers.
    Header names should match harmony properties.
    At least, 'harmony_or_key', 'time' and 'symbol' should be present.
    Returns an array with descriptions of any errors during the process.
    """
    errors = []

    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        try:
            header = next(reader)
        except StopIteration:
            return ["Can't import: file is empty."]

        attrs_with_parsers = [
            ("harmony_or_key", _parse_harmony_or_key),
            ("measure", int),
            ("fraction", _parse_measure_fraction),
            ("symbol", str),
            ("comments", str),
            ("display_mode", _parse_display_mode),
            ("custom_text", str),
            ("custom_text_font_type", _parse_custom_text_font_type),
        ]

        required_attrs = ["harmony_or_key", "measure", "symbol"]
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
                errors += _create_component(
                    attr_to_value["harmony_or_key"],
                    attr_to_value["symbol"],
                    harmony_tl,
                    time,
                )

        return errors
