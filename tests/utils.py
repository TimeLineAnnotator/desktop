import json
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from tilia.requests import get, Get, Post, post


def get_blank_file_data():
    return {
        "file_path": "",
        "media_path": "",
        "media_metadata": {
            "title": "Untitled",
            "notes": "",
            "composer": "",
            "tonality": "",
            "time signature": "",
            "performer": "",
            "performance year": "",
            "arranger": "",
            "composition year": "",
            "recording year": "",
            "form": "",
            "instrumentation": "",
            "genre": "",
            "lyrics": "",
        },
        "timelines": {
            "0": {
                "is_visible": True,
                "ordinal": 1,
                "height": 40,
                "kind": "SLIDER_TIMELINE",
                "components": {},
            }
        },
        "app_name": "TiLiA",
        "version": "0.1.1",
    }


def get_dummy_timeline_data(id: int = 1) -> dict[str, dict]:
    return {
        str(id): {
            "height": 220,
            "is_visible": True,
            "ordinal": 1,
            "name": "test",
            "kind": "HIERARCHY_TIMELINE",
            "components_hash": "",
            "components": {},
        }
    }


def get_tmp_file_with_dummy_timeline(tmp_path: Path) -> Path:
    file_data = get_blank_file_data()
    file_data["timelines"] = get_dummy_timeline_data()
    tmp_file = tmp_path / "test.tla"
    tmp_file.write_text(json.dumps(file_data), encoding="utf-8")

    return tmp_file


def get_method_patch_target(method: Callable) -> str:
    """
    To be used to get a patch target that is resilient
    to moving the class to a different module.
    This only works when patching the module where the class
    is defined.
    """
    return method.__module__ + "." + method.__qualname__


@contextmanager
def undoable():
    """
    Asserts whether state is handled correctly when undoing/redoing.
    Use this as a context manager around a call of user_actions.trigger.
    E.g.
    ```
    with undoable():
        user_actions.trigger(TiliaAction.MARKER_ADD)
    ```
    """
    state_before = get(Get.APP_STATE)
    yield
    state_after = get(Get.APP_STATE)
    post(Post.EDIT_UNDO)
    assert get(Get.APP_STATE) == state_before
    post(Post.EDIT_REDO)
    assert get(Get.APP_STATE) == state_after
