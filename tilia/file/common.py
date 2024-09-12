from __future__ import annotations

import json
import os
from pathlib import Path

import tilia.errors
from tilia.file.tilia_file import TiliaFile
from tilia.timelines.hash_timelines import hash_timeline_collection_data

JSON_CONFIG = {"indent": 2}


def are_tilia_data_equal(data1: dict, data2: dict) -> bool:
    """Returns True if data1 is equivalent to data2, False otherwise."""

    attrs_to_check = ["media_metadata", "timelines", "media_path"]

    for attr in attrs_to_check:
        if attr == "timelines":
            hash1 = hash_timeline_collection_data(data1["timelines"])
            hash2 = hash_timeline_collection_data(data2["timelines"])
            if hash1 != hash2:
                return False
        elif data1[attr] != data2[attr]:
            return False
    return True


def write_tilia_file_to_disk(file: TiliaFile, path: str | Path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(file.__dict__, f, **JSON_CONFIG)


def validate_save_path(path: Path):
    error = False
    error_message = ''
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