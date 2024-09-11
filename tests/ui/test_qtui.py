from pathlib import Path
from unittest.mock import patch, mock_open

import tilia.errors
from tests.mock import PatchGet, PatchGetMultiple, Serve
from tilia.requests import Get
from tilia.ui import actions
from tilia.ui.actions import TiliaAction
from tilia.ui.windows import WindowKind


class TestCreateTimeline:
    def test_create(self, tilia, tls):
        with PatchGet(
            "tilia.ui.timelines.collection.requests.args",
            Get.FROM_USER_STRING,
            ("", True),
        ):
            actions.trigger(TiliaAction.TIMELINES_ADD_HIERARCHY_TIMELINE)

        assert not tls.is_empty

    def test_create_without_media_loaded(self, tilia, tls):
        with PatchGetMultiple(
            "tilia.ui.timelines.collection.requests.args",
            {Get.MEDIA_DURATION: 0, Get.FROM_USER_STRING: ("", True)},
        ):
            actions.trigger(TiliaAction.TIMELINES_ADD_HIERARCHY_TIMELINE)

        assert tls.is_empty

    def test_open_inspector_window(self, qtui, tls, tluis):
        tls.create_timeline("hierarchy")
        tluis[0].select_all_elements()

        assert qtui.open_inspect_window() is not None

    def test_open_inspector_window_fails_when_no_elements_are_selected(self, qtui, tls):
        assert not qtui.open_inspect_window()

    def test_open_multiple_inspector_windows_fails(self, qtui, tls, tluis):
        tls.create_timeline("hierarchy")
        tluis[0].select_all_elements()
        qtui.on_window_open(WindowKind.INSPECT)

        with patch("tilia.ui.windows.inspect.Inspect") as mock:
            qtui.on_window_open(WindowKind.INSPECT)

        mock.assert_not_called()


class PatchImportFromCSV:
    def __init__(self, timeline_ui, time_or_measure, csv_data):
        self.timeline_ui = timeline_ui
        self.time_or_measure = time_or_measure
        self.csv_data = csv_data

    def __enter__(self):
        choose_mock = patch('tilia.ui.timelines.collection.collection.TimelineUIs.ask_choose_timeline').start()
        choose_mock.return_value = self.timeline_ui

        get_by_mock = patch('tilia.ui.qtui.QtUI._get_by_time_or_by_measure_from_user').start()
        get_by_mock.return_value = self.time_or_measure

        self.serve_mock = Serve(Get.FROM_USER_FILE_PATH, (True, Path()))
        self.serve_mock.__enter__()

        patch("builtins.open", mock_open(read_data=self.csv_data)).start()

        return self  # Return self or another value as needed

    def __exit__(self, exc_type, exc_val, exc_tb):
        patch.stopall()  # Stop all patches
        self.serve_mock.__exit__(exc_type, exc_val, exc_tb)


class TestImportFromCSV:
    def test_imported_data_is_set(self, qtui, tls, actions, tilia_state, marker_tlui):
        with PatchImportFromCSV(marker_tlui, 'time', 'time\n1\n2\n3'):
            actions.trigger(TiliaAction.MARKER_IMPORT_FROM_CSV)

        assert len(marker_tlui) == 3
        assert marker_tlui[0].get_data('time') == 1
        assert marker_tlui[1].get_data('time') == 2
        assert marker_tlui[2].get_data('time') == 3

        assert marker_tlui.imported_path == Path()
        assert marker_tlui.imported_method == 'time'

    @staticmethod
    def _reload_from_csv(actions, tlui, data1, data2):
        with PatchImportFromCSV(tlui, 'time', data1):
            actions.trigger(TiliaAction.MARKER_IMPORT_FROM_CSV)

        with Serve(Get.FROM_USER_YES_OR_NO, (True, True)):
            actions.trigger(TiliaAction.TIMELINES_CLEAR)
        assert tlui.is_empty
        with Serve(Get.CONTEXT_MENU_TIMELINE_UI, [tlui]):
            with patch('builtins.open', mock_open(read_data=data2)):
                actions.trigger(TiliaAction.TIMELINE_RELOAD_FROM_FILE)

    def test_reload(self, qtui, tls, actions, marker_tlui):
        data1 = 'time\n1\n2\n3'
        data2 = 'time\n1\n2\n3\n4'
        self._reload_from_csv(actions, marker_tlui, data1, data2)
        assert len(marker_tlui) == 4

    def _reload_with_error(self, actions, tlui, data, error_type: type(Exception)):
        with PatchImportFromCSV(tlui, 'time', data):
            actions.trigger(TiliaAction.MARKER_IMPORT_FROM_CSV)

        with Serve(Get.FROM_USER_YES_OR_NO, (True, True)):
            actions.trigger(TiliaAction.TIMELINES_CLEAR)

        with Serve(Get.CONTEXT_MENU_TIMELINE_UI, [tlui]):
            with patch('tilia.parsers.csv.base.TiliaCSVReader.__enter__') as mock:
                mock.side_effect = error_type
                actions.trigger(TiliaAction.TIMELINE_RELOAD_FROM_FILE)

    def test_reload_file_not_found(self, qtui, tls, actions, marker_tlui, tilia_errors):
        data = 'time\n1\n2\n3'
        self._reload_with_error(actions, marker_tlui, data, FileNotFoundError)
        tilia_errors.assert_error_equals(tilia.errors.CSV_FILE_NOT_FOUND)

    def test_reload_permission_denied(self, qtui, tls, actions, marker_tlui, tilia_errors):
        data = 'time\n1\n2\n3'
        self._reload_with_error(actions, marker_tlui, data, PermissionError)
        tilia_errors.assert_error_equals(tilia.errors.CSV_PERMISSION_DENIED)

    def test_reload_import_failed(self, qtui, tls, actions, marker_tlui, tilia_errors):
        data = 'time\n1\n2\n3'
        self._reload_with_error(actions, marker_tlui, data, ValueError)
        tilia_errors.assert_in_error_title(tilia.errors.CSV_IMPORT_FAILED.title)
        tilia_errors.assert_in_error_message('ValueError')
