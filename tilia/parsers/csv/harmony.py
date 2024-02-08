from pathlib import Path
from typing import Any, Optional

from tilia.parsers.csv.common import (
    _get_attrs_indices,
    _validate_required_attrs,
    _parse_attr_data,
    _get_attr_data,
)
from tilia.parsers.csv.csv import TiliaCSVReader
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.harmony.timeline import HarmonyTimeline


def import_by_time(
    timeline: HarmonyTimeline,
    path: Path,
    file_kwargs: Optional[dict[str, Any]] = None,
    reader_kwargs: Optional[dict[str, Any]] = None,
) -> list[str]:
    errors = []

    with TiliaCSVReader(path, file_kwargs, reader_kwargs) as reader:
        try:
            header = next(reader)
        except StopIteration:
            return ["Can't import: file is empty."]

        attrs_with_parsers = [
            ("harmony_or_key", str),
            ("time", float),
            ("symbol", str),
            ("comments", str),
            ("custom_text", str),
            ("custom_text_font_type", str),
        ]

        required_attrs = ["harmony_or_key", "time", "symbol"]

        indices = _get_attrs_indices([x[0] for x in attrs_with_parsers], header)

        if not _validate_required_attrs(required_attrs, indices):
            return errors

        attr_data = _get_attr_data(attrs_with_parsers, indices)

        for row_data in reader:
            if not row_data:
                continue

            component_type = row_data[indices[required_attrs.index("harmony_or_key")]]
            if component_type not in ["harmony", "key"]:
                errors += [
                    f"{component_type=} | {component_type} is not a valid value for 'harmony_or_key'. Must be 'harmony' or 'key'"
                ]
                continue

            success, row_errors, kwargs = _parse_attr_data(
                row_data, attr_data, required_attrs
            )
            errors += row_errors
            if not success:
                continue

            timeline.create_timeline_component(
                (
                    ComponentKind.HARMONY
                    if component_type == "harmony"
                    else ComponentKind.MODE
                ),
                **kwargs,
            )

        return errors


def import_by_measure(
    harmony_tl: HarmonyTimeline,
    beat_tl: BeatTimeline,
    path: Path,
    file_kwargs: Optional[dict[str, Any]] = None,
    reader_kwargs: Optional[dict[str, Any]] = None,
) -> list[str]:
    pass
