from __future__ import annotations

import json
import os
import re
from pathlib import Path

import tilia.constants
from tilia.file.tilia_file import TiliaFile

JSON_CONFIG = {"indent": 2}
# Kept by TiLiA's timelines from a file it read, and not in TiLiA 0.7's format,
# whose files the core refuses with a measure table or a measure source. This writer
# leaves them out, until TiLiA saves through the core
# (TimeLineAnnotator/project-management#449).
_NOT_IN_THE_OLD_FORMAT = ("measure_table", "measure_source", "fields")


def are_tilia_data_equal(data1: dict, data2: dict) -> bool:
    """Returns True if data1 is equivalent to data2, False otherwise."""
    for attr in ["media_metadata", "media_path", "timelines_hash"]:
        if data1[attr] != data2[attr]:
            return False
    component_hashes_1 = {
        tl_data["components_hash"] for tl_data in data1["timelines"].values()
    }
    component_hashes_2 = {
        tl_data["components_hash"] for tl_data in data2["timelines"].values()
    }
    if component_hashes_1 != component_hashes_2:
        return False

    return True


def write_tilia_file_to_disk(file: TiliaFile, path: str | Path):
    file.file_path = Path(file.file_path).as_posix()
    if file.media_path and not re.match(
        tilia.constants.YOUTUBE_URL_REGEX, file.media_path
    ):
        file.media_path = Path(file.media_path).as_posix()
    data = dict(file.__dict__)
    data["timelines"] = {
        id: {k: v for k, v in timeline.items() if k not in _NOT_IN_THE_OLD_FORMAT}
        for id, timeline in file.timelines.items()
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, **JSON_CONFIG)


def validate_save_path(path: Path):
    error = False
    error_message = ""
    if not path.parent.exists():
        error = True
        error_message = f"Parent directory {path.parent} does not exist."
    if path.parent.is_file():
        error = True
        error_message = f"Parent directory {path.parent} is a file."
    if not os.access(path.parent, os.W_OK):
        error = True
        error_message = f"Parent directory {path.parent} is not writable."

    return not error, error_message
