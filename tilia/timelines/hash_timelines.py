from typing import Callable, Any, Optional

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
import hashlib


def hash_function(string: str) -> str:
    return hashlib.md5(string.encode("utf-8")).hexdigest()


def hash_timeline_collection_data(timeline_collection_data: dict):
    sorted_tlcoll_data = sorted(
        timeline_collection_data.values(), key=lambda x: x["ordinal"]
    )

    str_to_hash = "|"
    for tl_data in sorted_tlcoll_data:
        str_to_hash += hash_timeline_data_by_kind(tl_data["kind"], tl_data) + "|"

    return hash_function(str_to_hash)


def hash_timeline_data_by_kind(kind: TimelineKind, tl_data: dict):
    match kind:
        case TimelineKind.SLIDER_TIMELINE.name:
            return hash_timeline_data(["is_visible", "height"], None, tl_data)
        case TimelineKind.OSCILLOGRAM_TIMELINE.name:
            return hash_timeline_data(["is_visible", "height", "name"], hash_oscillogram_data, tl_data)
        case TimelineKind.HIERARCHY_TIMELINE.name:
            return hash_timeline_data(
                ["height", "is_visible", "name"], hash_hierarchies_data, tl_data
            )
        case TimelineKind.MARKER_TIMELINE.name:
            return hash_timeline_data(
                ["height", "is_visible", "name"], hash_markers_data, tl_data
            )
        case TimelineKind.BEAT_TIMELINE.name:
            return hash_timeline_data(
                [
                    "height",
                    "is_visible",
                    "name",
                    "beat_pattern",
                    "beats_in_measure",
                    "measure_numbers",
                    "measures_to_force_display",
                ],
                hash_beat_data,
                tl_data,
            )
        case TimelineKind.HARMONY_TIMELINE.name:
            return hash_timeline_data(
                ["level_height", "level_count", "is_visible", "name"],
                hash_harmony_timeline_components_data,
                tl_data,
            )
        case _:
            raise NotImplementedError


def hash_timeline_data(
    hash_attributes: list[str],
    hash_components_func: Optional[Callable[[dict], str]],
    timeline_data: dict,
):
    str_to_hash = "|"
    for attr in hash_attributes:
        str_to_hash += str(timeline_data[attr]) + "|"

    if hash_components_func:
        str_to_hash += hash_components_func(timeline_data["components"]) + "|"

    return hash_function(str_to_hash)


def hash_timeline_components(
    hash_attributes: list[str], sort_func: Callable[[dict], Any], component_data: dict
):
    sorted_component_data = sorted(component_data.values(), key=sort_func)

    str_to_hash = "|"
    for data in sorted_component_data:
        for attr in hash_attributes:
            str_to_hash += str(data[attr]) + "|"

    return hash_function(str_to_hash)


def hash_harmony_timeline_components_data(components_data: dict) -> str:
    from tilia.timelines.harmony.components import Mode, Harmony

    def sort_harmonies(x):
        return x["level"], x["time"]

    harmony_data = {
        id: data
        for id, data in components_data.items()
        if data["kind"] == ComponentKind.HARMONY.name
    }
    harmonies_hash = hash_timeline_components(
        Harmony.SERIALIZABLE_BY_VALUE, sort_harmonies, harmony_data
    )

    def sort_modes(x):
        return x["level"], x["time"]

    mode_data = {
        id: data
        for id, data in components_data.items()
        if data["kind"] == ComponentKind.MODE.name
    }
    modes_hash = hash_timeline_components(
        Mode.SERIALIZABLE_BY_VALUE, sort_modes, mode_data
    )

    return hash_function(harmonies_hash + "|" + modes_hash)


def hash_hierarchies_data(hierarchy_data: dict) -> str:
    hash_attributes = [
        "start",
        "pre_start",
        "end",
        "level",
        "label",
        "formal_type",
        "formal_function",
        "comments",
        "color",
    ]

    def sort_func(x):
        return x["start"], x["level"]

    return hash_timeline_components(hash_attributes, sort_func, hierarchy_data)


def hash_markers_data(marker_data: dict) -> str:
    hash_attributes = ["time", "label", "comments", "color"]
    return hash_timeline_components(hash_attributes, lambda x: x["time"], marker_data)


def hash_beat_data(marker_data: dict) -> str:
    hash_attributes = ["time"]
    return hash_timeline_components(hash_attributes, lambda x: x["time"], marker_data)


def hash_harmony_data(harmony_data: dict) -> str:
    def sort_func(x):
        return x["level"], x["time"]

    hash_attributes = [
        "time",
        "step",
        "accidental",
        "quality",
        "inversion",
        "applied_to",
        "level",
        "comments",
    ]

    return hash_timeline_components(hash_attributes, sort_func, harmony_data)

def hash_oscillogram_data(oscillogram_data: dict) -> str:
    hash_attributes = ["start", "length", "amplitude"]
    return hash_timeline_components(hash_attributes, lambda x: x["start"], oscillogram_data)
