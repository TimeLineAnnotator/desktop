import os
from unittest.mock import MagicMock

import pytest

from tilia.globals_ import UserInterfaceKind
from tilia.main import TiLiA, FileManager
from tilia.timelines.timeline_kinds import TimelineKind


@pytest.fixture
def tilia_mock():
    tilia_mock_ = TiLiA(ui_kind=UserInterfaceKind.MOCK)
    return tilia_mock_


@pytest.fixture
def file_manager(tilia_mock):
    return FileManager(tilia_mock)


@pytest.fixture
def tlwui_builder(tilia_mock):
    # noinspection PyProtectedMember
    return tilia_mock._timeline_with_ui_builder


class TestFileManager:

    def test_constructor(self, tilia_mock):
        FileManager(tilia_mock)

    def test_open(self, monkeypatch, file_manager):

        # TODO remove hardcoded path
        file_manager._app.ui.get_file_open_path.return_value = 'C:\\Programação\\musan_pre_separation\\tests\\test_file.tla'
        file_manager.open()


class TestTimelineWithUIBuilder:

    def test_create_slider_timeline_no_error(self, tilia_mock, tlwui_builder):
        tlwui_builder.create_timeline(TimelineKind.SLIDER_TIMELINE, name='test')

    def test_create_hierarchy_timelin_no_error(self, tilia_mock, tlwui_builder):
        tlwui_builder.create_timeline(TimelineKind.HIERARCHY_TIMELINE, name='test')



