from __future__ import annotations

import json
import os
import re
from pathlib import Path

import tilia.constants
from tilia.file.tilia_file import TiliaFile

JSON_CONFIG = {"indent": 2}


def normalize_media_path(path: str) -> str:
    """Returns `path` as it is written to a file: POSIX if it is a local path,
    unchanged if it is a YouTube URL."""
    if path and not re.match(tilia.constants.YOUTUBE_URL_REGEX, path):
        return Path(path).as_posix()
    return path


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


TIMELINE_HASH_KEYS = ("hash", "components_hash")
COMPONENT_HASH_KEYS = ("hash",)


def _without_keys(data: dict, keys: tuple[str, ...]) -> dict:
    return {k: v for k, v in data.items() if k not in keys}


def strip_hashes(timelines: dict) -> dict:
    """Returns a copy of `timelines` without timeline and component hashes.

    Hashes are a runtime aid for undo and for detecting unsaved changes.
    They are recomputed from the timelines when a file is opened, so writing
    them to disk would only add noise to files and their diffs.
    """
    result = {}
    for tl_id, tl_data in timelines.items():
        if not isinstance(tl_data, dict):
            result[tl_id] = tl_data
            continue
        tl_data = _without_keys(tl_data, TIMELINE_HASH_KEYS)
        components = tl_data.get("components")
        if isinstance(components, dict):
            tl_data["components"] = {
                cmp_id: (
                    _without_keys(cmp_data, COMPONENT_HASH_KEYS)
                    if isinstance(cmp_data, dict)
                    else cmp_data
                )
                for cmp_id, cmp_data in components.items()
            }
        result[tl_id] = tl_data
    return result


def write_tilia_file_to_disk(file: TiliaFile, path: str | Path) -> None:
    file.file_path = Path(file.file_path).as_posix()
    file.media_path = normalize_media_path(file.media_path)
    # unknown_timelines are already folded into timelines in app.get_app_state().
    # The remaining unknown_timelines/deleted_timelines are runtime-only bookkeeping.
    # Hashes are recomputed on load (see strip_hashes).
    data = {
        k: v
        for k, v in file.__dict__.items()
        if k not in ("unknown_timelines", "deleted_timelines", "timelines_hash")
    }
    data["timelines"] = strip_hashes(data["timelines"])
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
