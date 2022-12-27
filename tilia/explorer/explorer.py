"""
Logic for parsing and searching through .tla files.
Files get converted to pandas DataFrames for that.
"""


import json
import os.path
from typing import Literal, Any

import pandas as pd

import tilia.globals_ as globals_
import tilia.events as events
from tilia.events import Event

from tilia.explorer.explorer_gui import ExplorerGUI, ExplorerTkGUI

import tilia.player.player as player
from tilia.explorer.explorer_types import MeasureLength

ATTRIBUTE_TYPES = {
    "length": float,
    "start": float,
    "end": float,
    "level": str,
    "start_measure": int,
    "start_beat": int,
    "end_measure": int,
    "end_beat": int,
    "measure_length": MeasureLength,
}


def get_objects_list(timeline_objects_dict: dict) -> list:
    obj_list = []
    for save_id, value in timeline_objects_dict.items():
        value["save_id"] = save_id
        obj_list.append(value)

    return obj_list


def preprocess_hierarchy_timeline_objs(
    timeline_objs_dict: dict, measures_list: list
) -> dict:
    processed_dict = flatten_levels_into_attributes(timeline_objs_dict)
    processed_dict = add_other_searchable_attributes(processed_dict, measures_list)

    return processed_dict


def flatten_levels_into_attributes(timeline_objs_dict: dict) -> dict:
    flattened_dict = {}
    for level, units in timeline_objs_dict.items():
        for save_id, unit_dict in units.items():
            new_unit_dict = unit_dict.copy()
            new_unit_dict["level"] = level
            flattened_dict[save_id] = new_unit_dict

    return flattened_dict


def add_other_searchable_attributes(units: dict, measures: list) -> dict:
    for _, unit in units.items():
        unit["length"] = unit["end"] - unit["start"]
        start_data = get_start_measure_and_beat(unit, measures)
        end_data = get_end_measure_and_beat(unit, measures)
        unit["start_measure"] = start_data["number"]
        unit["start_beat"] = start_data["beat_number"]
        unit["end_measure"] = end_data["number"]
        unit["end_beat"] = end_data["beat_number"]
        unit["measure_length"] = get_measure_length(start_data, end_data)
        unit["measure_start"] = f"{start_data['number']}.{start_data['beat_number']}"
        unit["measure_end"] = f"{end_data['number']}.{end_data['beat_number']}"

    return units


def get_measure_length(
    start_data: dict[str, int], end_data: dict[str, int]
) -> MeasureLength:
    beats_from_start = start_data["beats_in_measure"] - start_data["beat_number"] + 1
    beats_from_end = end_data["beat_number"] - 1
    beat_sum = beats_from_start + beats_from_end
    measure_part = (
        end_data["abs_number"]
        - start_data["abs_number"]
        + (beat_sum // end_data["beats_in_measure"])
        - 1
    )
    beat_part = beat_sum % end_data["beats_in_measure"]

    return MeasureLength(measure_part, beat_part)


def get_start_measure_and_beat(unit: dict, measures: list) -> dict[str:int]:
    try:
        start_measure = [
            m for m in measures if m[1]["start"] <= unit["start"] < m[1]["end"]
        ][0]
        measure_number = start_measure[1]["number"]
        measure_abs_number = start_measure[1]["abs_number"]
        beat_number = get_nearest_beat_number(unit["start"], start_measure)
        beats_in_measure = start_measure[1]["beats_per_measure"]
    except IndexError:
        # unit starts before first beat
        if unit["start"] < measures[0][1]["start"]:
            measure_number, measure_abs_number, beat_number, beats_in_measure = (
                1,
                1,
                1,
                measures[0][1]["beats_per_measure"],
            )
        # unit starts after last beat
        elif unit["start"] > measures[-1][1]["start"]:
            measure_number, measure_abs_number, beat_number, beats_in_measure = (
                measures[-1][1]["number"],
                measures[-1][1]["abs_number"],
                measures[-1][1]["beats_per_measure"],
                measures[-1][1]["beats_per_measure"],
            )

        else:
            raise ValueError(
                f"Can't assing start measure and/or start beat to unit {unit}"
            )

    return_data = {
        "number": measure_number,
        "abs_number": measure_abs_number,
        "beat_number": beat_number,
        "beats_in_measure": beats_in_measure,
    }

    return return_data


def get_end_measure_and_beat(unit: dict, measures: list) -> dict[str:int]:
    try:
        end_measure = [
            m for m in measures if m[1]["start"] <= unit["end"] < m[1]["end"]
        ][0]
        measure_number = end_measure[1]["number"]
        measure_abs_number = end_measure[1]["abs_number"]
        beat_number = get_nearest_beat_number(unit["end"], end_measure)
        beats_in_measure = end_measure[1]["beats_per_measure"]
    except IndexError:
        # unit ends before first beat
        if unit["end"] < measures[0][1]["start"]:
            measure_number, measure_abs_number, beat_number, beats_in_measure = (
                1,
                1,
                1,
                1,
            )
        # unit ends after last beat
        elif unit["end"] > measures[-1][1]["end"]:
            measure_number, measure_abs_number, beat_number, beats_in_measure = (
                measures[-1][1]["number"],
                measures[-1][1]["abs_number"],
                measures[-1][1]["beats_per_measure"],
                measures[-1][1]["beats_per_measure"],
            )

        else:
            raise ValueError(f"Can't assing end measure and/or end beat to unit {unit}")

    return_data = {
        "number": measure_number,
        "abs_number": measure_abs_number,
        "beat_number": beat_number,
        "beats_in_measure": beats_in_measure,
    }

    return return_data


def get_nearest_beat_number(reference_time: float, measure: tuple[str, dict]) -> int:
    distance = 99999999
    nearest_beat_number = None
    for beat_number, beat_time in measure[1]["beats"].items():
        if abs(reference_time - beat_time) < distance:
            distance = abs(reference_time - float(beat_time))
            nearest_beat_number = beat_number

    return int(nearest_beat_number)


def preprocess_object_dict(
    timeline_objects_dict: dict, timeline_type: str, measures_list: list
) -> dict:
    if timeline_type == "HierarchyTimeline":
        return preprocess_hierarchy_timeline_objs(timeline_objects_dict, measures_list)
    else:
        return timeline_objects_dict


def get_objects_dataframe(
    timeline_objects_dict: dict, timeline_type: str, measures_list: list
) -> pd.DataFrame:
    processed_objs_dict = preprocess_object_dict(
        timeline_objects_dict, timeline_type, measures_list
    )
    return pd.DataFrame(get_objects_list(processed_objs_dict))


def add_start_and_end_attributes_to_measure(
    measure: tuple[str, dict], next_measure: tuple[str, dict] | None
):
    measure[1]["start"] = measure[1]["beats"]["1"]
    if next_measure:
        measure[1]["end"] = next_measure[1]["beats"]["1"]
    else:
        last_beat_time = max(measure[1]["beats"].values())
        measure[1]["end"] = last_beat_time
        # backlog: uses last beat time as end attribute on last beat, which is not accurate.


def get_beat_timeline_dict_for_attr_calc(file_dict: dict):
    measure_list = []
    for key, value in file_dict["timelines"].items():
        if key.startswith("BeatTimeline"):
            measure_list = [
                (number, info)
                for number, info in value["main_objects"]["measures"].items()
            ]
            try:
                measure_list = sorted(measure_list, key=lambda x: x[1]["beats"]["1"])
            except KeyError:
                empty_measures = [
                    m[1]["abs_number"] for m in measure_list if not m[1].get("beats")
                ]
                raise KeyError(
                    f"Found empty measure with abs_number={empty_measures}, can't continue measure ordering."
                )

            for i, measure in enumerate(measure_list[:-1]):
                add_start_and_end_attributes_to_measure(measure, measure_list[i + 1])
            add_start_and_end_attributes_to_measure(measure_list[-1], None)

    return measure_list


def filter_tlobjects_dataframe(
    df: pd.DataFrame,
    attr: str,
    value: str | tuple[str, str],
    search_mode: str,
    negate: bool,
    inclusive: bool = False,
    regex: bool = False,
) -> pd.DataFrame:

    if attr in ATTRIBUTE_TYPES.keys():
        attr_type = ATTRIBUTE_TYPES[attr]
    else:
        # default type is str
        attr_type = str

    if attr_type == float:
        value = float(value)
    elif attr_type == int:
        value = int(value)
    elif attr_type == MeasureLength:
        value = MeasureLength.from_str(value)

    if not regex and isinstance(value, str):
        # for later implementation
        # value = re.escape(value)
        pass

    match search_mode, inclusive:
        case "EQUALS", _:
            if attr_type == str:
                bool_array = df[attr].str.lower() == value.lower()
            else:
                bool_array = df[attr] == value
        case "EQUALS", _:
            bool_array = df[attr] == value
        case "CONTAINS", _:
            bool_array = df[attr].str.contains(value, case=False, regex=False)
        case "GREATER", False:
            bool_array = df[attr] > value
        case "GREATER", True:
            bool_array = df[attr] >= value
        case "SMALLER", False:
            bool_array = df[attr] < value
        case "SMALLER", True:
            bool_array = df[attr] <= value
        case "BETWEEN", True:
            bool_array = df[attr].between(*value, inclusive="both")
        case "BETWEEN", False:
            bool_array = df[attr].between(*value, inclusive="neither")
        case _:
            raise ValueError(f"'{search_mode}' is not a valid search type.")

    if negate:
        bool_array = [not value for value in bool_array]

    return df.loc[bool_array]


# noinspection PyUnusedLocal
def get_timeline_title_str(timeline_type: str, timeline_dict: dict) -> str:
    return timeline_dict["label_text"]


def get_timelines_from_file_dict(
    file_dict: dict, timeline_type: str
) -> list[tuple[str, pd.DataFrame]]:
    measures_for_calc = get_beat_timeline_dict_for_attr_calc(file_dict)

    timelines_to_search = []
    for key, value in file_dict["timelines"].items():
        if key.startswith(timeline_type):
            df = get_objects_dataframe(
                value["main_objects"], timeline_type, measures_for_calc
            )

            timelines_to_search.append(
                (get_timeline_title_str(timeline_type, value), df.sort_values("start"))
            )

    return timelines_to_search


def search_in_tlobjects_df(
    timeline: pd.DataFrame,
    search_params: list[tuple],
    search_mode: Literal["ALL", "ANY"],
) -> pd.DataFrame:
    filtered_df = timeline

    if not search_params:
        return timeline

    if search_mode == "ALL":
        for params in search_params:
            filtered_df = filter_tlobjects_dataframe(filtered_df, *params)
    elif search_mode == "ANY":
        filtered_dfs = []
        for params in search_params:
            filtered_dfs.append(filter_tlobjects_dataframe(timeline, *params))
        filtered_df = pd.concat(filtered_dfs).sort_values("start")
    else:
        raise ValueError(
            f"Can't filter timeline objects dataframe: invalid search mode '{search_mode}"
        )

    return filtered_df


def search_in_file_dict(
    file_dict: dict,
    timeline_type: str,
    search_params: list[tuple],
    match_kind: Literal["ALL", "ANY"],
) -> pd.DataFrame:

    timelines_to_search = get_timelines_from_file_dict(file_dict, timeline_type)
    accumulated_result = search_in_tlobjects_df(
        timelines_to_search[0][1], search_params, match_kind
    )
    accumulated_result["timeline"] = timelines_to_search[0][0]

    for timeline in timelines_to_search[1:]:
        timeline_result = search_in_tlobjects_df(timeline[1], search_params, match_kind)
        timeline_result["timeline"] = timeline[0]
        accumulated_result = pd.concat([accumulated_result, timeline_result])

    return accumulated_result


def format_search_result(result: pd.DataFrame, column_order: list[str]) -> pd.DataFrame:
    formatted_result = result[column_order]
    return formatted_result


def get_app_files_from_dir(dir_path: str) -> list[str]:
    from os.path import isfile, join

    return [
        join(dir_path, f)
        for f in os.listdir(dir_path)
        if isfile(join(dir_path, f)) and f.endswith(f"{globals_.FILE_EXTENSION}")
    ]


def filter_files_by_attrs(
    file_path_list: list[str],
    search_params: list[tuple],
    search_mode: Literal["ALL", "ANY"],
) -> list[str]:

    if not search_params:
        return file_path_list

    files_matched = []
    for path in file_path_list:

        with open(path, "r") as sample_file:
            file_dict = json.load(sample_file)

        if search_mode == "ANY":
            is_match = match_file_to_any_condition(file_dict, search_params)
        elif search_mode == "ALL":
            is_match = match_file_to_all_conditions(file_dict, search_params)
        else:
            raise ValueError(f"Can't filter files: Invalid search mode '{search_mode}")

        if is_match:
            files_matched.append(path)

    return files_matched


def match_file_to_any_condition(file_dict: dict, conditions: list[tuple]) -> bool:
    for condition in conditions:
        if match_file_to_condition(file_dict, *condition):
            return True

    return False


def match_file_to_all_conditions(file_dict: dict, conditions: list[tuple]) -> bool:
    for condition in conditions:
        if not match_file_to_condition(file_dict, *condition):
            return False

    return True


def match_file_to_condition(
    file_dict: dict, attr: str, search_value: Any, search_mode: str, negate: bool
) -> bool:
    match search_mode:
        case "EQUALS":
            is_match = (
                file_dict["_media_metadata"][attr].lower() == search_value.lower()
            )
        case "CONTAINS":
            is_match = (
                search_value.lower() in file_dict["_media_metadata"][attr].lower()
            )
        case "GREATER":
            is_match = file_dict["_media_metadata"][attr].lower() > search_value.lower()
        case "SMALLER":
            is_match = file_dict["_media_metadata"][attr].lower() < search_value.lower()
        case "BETWEEN":
            is_match = (
                search_value[0].lower()
                <= file_dict["_media_metadata"][attr].lower()
                <= search_value[1].lower()
            )
        case _:
            raise ValueError(f"'{search_mode}' is not a valid search type.")

    if negate:
        is_match = not is_match

    return is_match


def add_file_data(
    search_result: pd.DataFrame, fields_to_add: list[str], file_dict: dict
):
    for field in fields_to_add:
        search_result[field] = file_dict["_media_metadata"][field]

    search_result["audio_path"] = file_dict["audio_path"]

    return search_result


def search_tlobjects_in_files(
    file_paths: list[str],
    timeline_type: str,
    search_params: list[tuple],
    match_type: Literal["ALL", "ANY"],
    columns_to_display: list[str],
    file_data_to_add: list[str],
) -> tuple[pd.DataFrame, dict] | tuple[None, None]:
    complete_file_results = []
    formatted_file_results = []

    for file_path in file_paths:
        with open(file_path, "r") as sample_file:
            file_dict = json.load(sample_file)

        complete_single_file_result = search_in_file_dict(
            file_dict, timeline_type, search_params, match_type
        )

        complete_single_file_result["file_name"] = os.path.basename(file_path)
        complete_single_file_result = add_file_data(
            complete_single_file_result, file_data_to_add, file_dict
        )
        formatted_single_file_result = format_search_result(
            complete_single_file_result, columns_to_display
        )

        complete_file_results.append(complete_single_file_result)
        formatted_file_results.append(formatted_single_file_result)

    if not complete_file_results:
        return None, None

    final_formatted_result = pd.concat(formatted_file_results, ignore_index=True)
    final_complete_result = pd.concat(complete_file_results, ignore_index=True)
    final_audio_info = final_complete_result[["audio_path", "start", "end"]].T.to_dict()

    return final_formatted_result, final_audio_info


class Explorer:
    def __init__(self):
        self.curr_audio_index = -1
        self.audio_info = None
        events.subscribe(self, "EXPLORER: SEARCH", do_search)
        events.subscribe(self, "EXPLORER: LOAD MEDIA", self.on_explorer_load_media)
        events.subscribe(self, "EXPLORER: PLAY", self.on_explorer_play)
        events.subscribe(
            self,
            "EXPLORER: AUDIO INFO FROM SEARCH RESULT",
            self.on_explorer_audio_info_from_search_result,
        )

    def on_explorer_load_media(self, audio_index: int):
        self.curr_audio_index = audio_index
        curr_audio = self.audio_info[self.curr_audio_index]
        events.post(
            "PLAYER: LOAD MEDIA",
            curr_audio["audio_path"],
            curr_audio["start"],
            curr_audio["end"],
        )

    def on_explorer_play(self):
        events.post(Event.PLAYER_REQUEST_TO_PLAYPAUSE)

    def on_explorer_audio_info_from_search_result(self, audio_info):
        self.audio_info = audio_info


def do_search(
    files_dir: str,
    file_search_params: list[tuple],
    file_match_type: Literal["ALL", "ANY"],
    timeline_type: str,
    timeline_search_params: list[tuple],
    timeline_match_type: Literal["ALL", "ANY"],
    column_order: list[str],
    file_data_to_add: list[str],
):
    app_files = get_app_files_from_dir(files_dir)

    files_to_search = filter_files_by_attrs(
        app_files, file_search_params, file_match_type
    )

    search_result, audio_info = search_tlobjects_in_files(
        files_to_search,
        timeline_type,
        timeline_search_params,
        timeline_match_type,
        column_order,
        file_data_to_add,
    )

    events.post(events.EventEXPLORER_AUDIO_INFO_FROM_SEARCH_RESULT, audio_info)
    events.post(events.EventEXPLORER_DISPLAY_SEARCH_RESULTS, search_result)


def main():

    import tkinter as tk

    root = tk.Tk()
    root.title(f"{globals_.APP_NAME} Explorer")
    player.PygamePlayer()
    gui = ExplorerTkGUI(root)
    Explorer(gui)
    gui.pack()
    root.mainloop()


if __name__ == "__main__":
    main()
