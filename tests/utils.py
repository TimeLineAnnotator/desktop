import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path
from pprint import pformat
from typing import Callable

from PyQt6.QtWidgets import QMenu

from tilia.requests import get, Get
from tests.mock import patch_file_dialog
from tilia.ui import commands
from tilia.ui.commands import CommandQAction


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
    Use this as a context manager around a call of commands.execute.
    E.g.
    ```
    with undoable():
        commands.execute("timeline.marker.add")
    ```
    """
    state_before = get(Get.APP_STATE)
    yield
    state_after = get(Get.APP_STATE)
    commands.execute("edit.undo")

    try:
        assert get(Get.APP_STATE) == state_before
    except AssertionError as e:
        if importlib.util.find_spec("deepdiff") is None:
            state_diff = (
                "Consider installing `deepdiff` library for debugging app states."
            )
        else:
            import deepdiff

            state_diff = pformat(deepdiff.DeepDiff(get(Get.APP_STATE), state_before))
        raise AssertionError("Undoing did not preserve state.\n" + state_diff) from e

    commands.execute("edit.redo")
    try:
        assert get(Get.APP_STATE) == state_after
    except AssertionError as e:
        if importlib.util.find_spec("deepdiff") is None:
            state_diff = (
                "Consider installing `deepdiff` library for debugging app states."
            )
        else:
            import deepdiff

            state_diff = pformat(deepdiff.DeepDiff(get(Get.APP_STATE), state_after))
        raise AssertionError("Redoing did not preserve state.\n" + state_diff) from e


def reloadable(save_path):
    """
    Ensures the file loads similarly after saving and loading.
    Use this as a decorator for a function that checks for the correct values.
    E.g. (See tests.ui.timelines.score.test_score_timeline_ui.test_attribute_positions)
    ```
    @reloadable(save_path)
    def check_values(): ...
    ```
    """

    def check_and_reload(checks):
        checks()

        with patch_file_dialog(True, [save_path, save_path]):
            commands.execute("file.save")
            commands.execute("file.open")

        checks()

    return check_and_reload


def get_command_action(menu: QMenu, command_name: str) -> CommandQAction | None:
    for action in menu.actions():
        if isinstance(action, CommandQAction) and action.command_name == command_name:
            return action
    return None


def get_command_names(menu: QMenu) -> list[str]:
    command_names = []
    for action in menu.actions():
        if isinstance(action, CommandQAction):
            command_names.append(action.command_name)
    return command_names


def get_submenu(menu, name):
    for action in menu.actions():
        if action.text().replace("&", "") == name:
            return action.menu()
    return None


def get_main_window_menu(qtui, name):
    menu_names = [
        x.text().replace("&", "") for x in qtui.main_window.menuBar().actions()
    ]
    menu_idx = menu_names.index(name)
    return qtui.main_window.menuBar().actions()[menu_idx].menu()


def get_actions_in_menu(menu: QMenu):
    return [action for action in menu.actions() if not action.isSeparator()]
