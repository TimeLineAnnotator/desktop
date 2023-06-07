from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from tilia.file.tilia_file import TiliaFile
from tilia.timelines.hash_timelines import hash_timeline_collection_data

JSON_CONFIG = {"indent": 2}


def compare_tilia_data(data1: dict, data2: dict) -> bool:
    """Returns True if data1 is equivalent to data2, False otherwise."""

    ATTRS_TO_CHECK = ["media_metadata", "timelines", "media_path"]

    for attr in ATTRS_TO_CHECK:
        if attr == "timelines":
            if hash_timeline_collection_data(
                data1["timelines"]
            ) != hash_timeline_collection_data(data2["timelines"]):
                return False
        elif data1[attr] != data2[attr]:
            return False
    return True


def write_tilia_file_to_disk(file: TiliaFile, path: str | Path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dataclasses.asdict(file), f, **JSON_CONFIG)
