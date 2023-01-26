import itertools
import os
from pathlib import Path

import pytest
from tilia import dirs

from tilia import settings
import tkinter as tk
import _tkinter

from tilia.events import unsubscribe_from_all
from tilia.timelines.state_actions import Action


@pytest.fixture(scope="session", autouse=True)
def tilia_session():
    def settings_get_patch(table, value, default_value=None):
        match table, value:
            case "dev", "dev_mode":
                return False
            case "auto-save", "interval":
                return 0
            case _:
                return original_settings_get(table, value)

    original_settings_get = settings.get
    settings.get = settings_get_patch

    dirs.setup_dirs()
    settings.load(dirs.settings_path)
    return


@pytest.fixture(scope="session")
def tk_session():
    pytest.root = tk.Tk()
    pump_events()
    yield
    if pytest.root:
        pytest.root.destroy()
        pump_events()


def pump_events():
    while pytest.root.dooneevent(_tkinter.ALL_EVENTS | _tkinter.DONT_WAIT):
        pass


@pytest.fixture(scope="session")
def tkui(tk_session):
    from tilia.ui.tkinterui import TkinterUI

    os.chdir(Path(Path(__file__).absolute().parents[1], "tilia"))
    tkui_ = TkinterUI(pytest.root)
    yield tkui_


# noinspection PyProtectedMember
@pytest.fixture(scope="module")
def tilia(tkui):
    from tilia._tilia import TiLiA

    tilia_ = TiLiA(tkui)
    tilia_._timeline_collection.delete_timeline(tilia_._timeline_collection[0])
    yield tilia_
    tilia_.clear_app()
    unsubscribe_from_all(tilia_._timeline_collection)
    unsubscribe_from_all(tilia_._timeline_ui_collection)
    unsubscribe_from_all(tilia_._file_manager)
    unsubscribe_from_all(tilia_._player)
    unsubscribe_from_all(tilia_._undo_manager)


@pytest.fixture(scope="module")
def tlui_clct(tkui, tilia):
    return tilia._timeline_ui_collection


@pytest.fixture(scope="module")
def tl_clct(tkui, tilia):
    return tilia._timeline_collection
