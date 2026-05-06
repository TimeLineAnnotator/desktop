import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path
from pprint import pformat
from typing import Callable
from unittest.mock import patch

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QToolButton, QWidgetAction

from tests.mock import patch_ask_for_string_dialog, patch_file_dialog
from tilia.requests import Get, Post, get, post
from tilia.ui import commands
from tilia.ui.commands import CommandQAction
from tilia.ui.timelines.base.context_menus import TimelineUIContextMenu
from tilia.ui.timelines.base.timeline import TimelineUI

EXAMPLE_VIDEO_FILENAME = "example.mp4"
EXAMPLE_YOUTUBE_URL = "https://www.youtube.com/watch?v=wBfVsucRe1w"


def load_local_media(path: str | Path):
    """Run the `media.load.local` command with the file dialog patched to
    return `path`."""
    with patch_file_dialog(True, [str(path)]):
        commands.execute("media.load.local")


def load_youtube_media(url: str = EXAMPLE_YOUTUBE_URL):
    """Run the `media.load.youtube` command with the URL prompt patched to
    return `url`."""
    with patch_ask_for_string_dialog(True, url):
        commands.execute("media.load.youtube")


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
                "kind": "Slider",
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
            "kind": "Hierarchy",
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
def assert_timeline_ui_update(tlui: TimelineUI, attr: str):
    method_name = f"update_{attr}"
    method = getattr(tlui, method_name)
    with patch.object(tlui, method_name, wraps=method) as spy:
        yield spy
    spy.assert_called()


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


def get_action_by_object_name(menu: QMenu, name: str) -> QAction | None:
    for action in menu.actions():
        if action.objectName() == name:
            return action
    return None


def get_command_action(menu: QMenu, command_name: str) -> CommandQAction | None:
    for action in menu.actions():
        if isinstance(action, CommandQAction) and action.command_name == command_name:
            return action
        # Toolbars that group buttons inside container widgets (e.g. ribbon-style
        # sections) expose those buttons via QWidgetAction; walk into their
        # default widget to find the underlying CommandQAction.
        if isinstance(action, QWidgetAction):
            widget = action.defaultWidget()
            if widget is None:
                continue
            for btn in widget.findChildren(QToolButton):
                btn_action = btn.defaultAction()
                if (
                    isinstance(btn_action, CommandQAction)
                    and btn_action.command_name == command_name
                ):
                    return btn_action
    return None


def get_command_from_toolbar(
    timeline_ui: TimelineUI, command_name: str
) -> QAction | None:
    return get_command_action(timeline_ui.TOOLBAR_CLASS(), command_name)


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


def get_context_menu(
    timeline_ui: TimelineUI, x: int = 0, y: int = 0
) -> TimelineUIContextMenu:
    return timeline_ui.CONTEXT_MENU_CLASS(timeline_ui, x, y)


def get_main_window_menu(qtui, name):
    menu_names = [
        x.text().replace("&", "") for x in qtui.main_window.menuBar().actions()
    ]
    menu_idx = menu_names.index(name)
    return qtui.main_window.menuBar().actions()[menu_idx].menu()


def get_actions_in_menu(menu: QMenu):
    return [action for action in menu.actions() if not action.isSeparator()]


def save_tilia_to_tmp_path(tmp_path, filename: str = "test") -> str:
    tmp_file_path = (tmp_path / (filename + ".tla")).resolve().__str__()
    with patch_file_dialog(True, [tmp_file_path]):
        commands.execute("file.save_as")
    return tmp_file_path


def save_and_reopen(tmp_path, filename: str = "test") -> None:
    file_path = save_tilia_to_tmp_path(tmp_path, filename)
    post(Post.APP_CLEAR)
    commands.execute("file.open", path=file_path)
