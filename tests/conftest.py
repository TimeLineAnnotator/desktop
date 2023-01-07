import os
from pathlib import Path

import pytest
from tilia import settings
import tkinter as tk
import _tkinter

from tilia._tilia import TiLiA
from tilia.ui.tkinterui import TkinterUI
from tilia.timelines.collection import TimelineCollection
from tilia.ui.timelines.collection import TimelineUICollection


@pytest.fixture(scope="session", autouse=True)
def tilia_session():
    prev_dev_mode_value = settings.settings["dev"]["dev_mode"]
    settings.edit_setting("dev", "dev_mode", False)
    yield
    settings.edit_setting("dev", "dev_mode", prev_dev_mode_value)


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
    os.chdir(Path(Path(__file__).absolute().parents[1], "tilia"))
    tkui_ = TkinterUI(pytest.root)
    yield tkui_


@pytest.fixture(scope="session")
def tilia(tkui):
    return TiLiA(tkui)


@pytest.fixture(scope="session")
def tlui_clct(tkui, tilia):
    return tilia._timeline_ui_collection


@pytest.fixture(scope="session")
def tl_clct(tkui, tilia):
    return tilia._timeline_collection
