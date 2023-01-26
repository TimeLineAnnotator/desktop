import os.path
import time
import tkinter as tk
from collections import OrderedDict
from unittest.mock import patch, PropertyMock

import pytest

from tilia.ui.tkinterui import TkinterUI
from tests.conftest import pump_events
from tilia.ui.windows import WindowKind


class TiliaDummy:
    def __init__(self):
        self.media_length = 99
        self.media_metadata = {"title": "test"}

    @property
    def media_path(self):
        return "test_path"


class TestTkinterUI:
    @patch("tilia.ui.tkinterui.Inspect")
    def test_on_request_window_inspect(self, inspect_mock, tkui):

        tkui.on_request_window(WindowKind.INSPECT)
        assert inspect_mock.called

        tkui.on_request_window(WindowKind.INSPECT)
        assert tkui._windows[WindowKind.INSPECT].focus.called

    @patch("tilia.ui.tkinterui.ManageTimelines")
    def test_on_request_window_manage_timelines(self, managetl_mock, tkui):
        tkui.on_request_window(WindowKind.MANAGE_TIMELINES)
        assert managetl_mock.called

    @patch("tilia.ui.tkinterui.MediaMetadataWindow")
    def test_on_request_window_media_metadata(self, mmtdata_mock, tkui):
        tkui.on_request_window(WindowKind.MEDIA_METADATA)
        assert mmtdata_mock.called

    @patch("tilia.ui.tkinterui.About")
    def test_on_request_window_about(self, about_mock, tkui):
        tkui.on_request_window(WindowKind.ABOUT)
        assert about_mock.called
