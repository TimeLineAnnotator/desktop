from pathlib import Path
from unittest.mock import patch, mock_open

import tilia.errors
from tests.mock import PatchGet, PatchGetMultiple, Serve
from tilia.requests import Get, post, Post
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

    def test_open_multiple_inspector_windows_fails(self, qtui, tls, tluis):
        tls.create_timeline("hierarchy")
        tluis[0].select_all_elements()
        qtui.on_window_open(WindowKind.INSPECT)

        with patch("tilia.ui.windows.inspect.Inspect") as mock:
            qtui.on_window_open(WindowKind.INSPECT)

        mock.assert_not_called()


class PatchImportFromCSV:
    def __init__(self, timeline_ui, time_or_measure, csv_data, beat_tlui=None):
        self.timeline_ui = timeline_ui
        self.beat_tlui = beat_tlui
        self.time_or_measure = time_or_measure
        self.csv_data = csv_data

    def __enter__(self):
        choose_mock = patch('tilia.ui.timelines.collection.collection.TimelineUIs.ask_choose_timeline').start()
        choose_mock.side_effect = [self.timeline_ui, self.beat_tlui]

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
    @staticmethod
    def _reload_from_csv(actions, tlui, time_or_measure, data1, data2, beat_tlui=None):
        # first import
        with PatchImportFromCSV(tlui, time_or_measure, data1, beat_tlui=beat_tlui):
            actions.trigger(TiliaAction.MARKER_IMPORT_FROM_CSV)

        # make changes to timeline
        with Serve(Get.FROM_USER_YES_OR_NO, (True, True)):
            tlui.select_all_elements()
            actions.trigger(TiliaAction.TIMELINE_ELEMENT_DELETE)
        assert tlui.is_empty

        # reload from file
        with Serve(Get.CONTEXT_MENU_TIMELINE_UI, [tlui]):
            with patch('builtins.open', mock_open(read_data=data2)):
                actions.trigger(TiliaAction.TIMELINE_RELOAD_FROM_FILE)

    def test_imported_data_is_set(self, qtui, tls, actions, tilia_state, marker_tlui):
        with PatchImportFromCSV(marker_tlui, 'time', 'time\n1\n2\n3'):
            actions.trigger(TiliaAction.MARKER_IMPORT_FROM_CSV)

        assert len(marker_tlui) == 3
        assert marker_tlui[0].get_data('time') == 1
        assert marker_tlui[1].get_data('time') == 2
        assert marker_tlui[2].get_data('time') == 3

        assert marker_tlui.imported_path == Path()
        assert marker_tlui.imported_method == 'time'
        assert marker_tlui.imported_beat_timeline_id is None

    def test_imported_data_is_set_with_measure(self, actions, tilia_state, marker_tlui, beat_tlui):
        beat_tlui.timeline.beat_pattern = [1]
        for i in range(4):
            tilia_state.current_time = i
            actions.trigger(TiliaAction.BEAT_ADD)

        with PatchImportFromCSV(marker_tlui, 'measure', 'measure\n1\n2\n3\n4', beat_tlui):
            actions.trigger(TiliaAction.MARKER_IMPORT_FROM_CSV)

        assert len(marker_tlui) == 4
        for i in range(4):
            assert marker_tlui[i].get_data('time') == i

        assert marker_tlui.imported_path == Path()
        assert marker_tlui.imported_method == 'measure'
        assert marker_tlui.imported_beat_timeline_id == beat_tlui.timeline.id

    def test_reload_by_measure(self, actions, marker_tlui, beat_tlui, tilia_state):
        beat_tlui.timeline.beat_pattern = [1]
        for i in range(4):
            tilia_state.current_time = i
            actions.trigger(TiliaAction.BEAT_ADD)

        data1 = 'measure\n1\n2\n3'
        data2 = 'measure\n1\n2\n3\n4'
        self._reload_from_csv(actions, marker_tlui, 'measure', data1, data2, beat_tlui=beat_tlui)
        assert len(marker_tlui) == 4

    def test_reload_by_measure_fails_when_beat_tl_deleted(self, actions, tilia_errors, marker_tlui, beat_tlui, tilia_state):
        beat_tlui.timeline.beat_pattern = [1]
        for i in range(4):
            tilia_state.current_time = i
            actions.trigger(TiliaAction.BEAT_ADD)

        data1 = 'measure\n1\n2\n3'

        with PatchImportFromCSV(marker_tlui, 'measure', data1, beat_tlui=beat_tlui):
            actions.trigger(TiliaAction.MARKER_IMPORT_FROM_CSV)

        with Serve(Get.CONTEXT_MENU_TIMELINE_UI, [beat_tlui]):
            with Serve(Get.FROM_USER_YES_OR_NO, (True, True)):
                post(Post.TIMELINE_DELETE_FROM_CONTEXT_MENU)

        with Serve(Get.CONTEXT_MENU_TIMELINE_UI, [marker_tlui]):
            actions.trigger(TiliaAction.TIMELINE_RELOAD_FROM_FILE)

        tilia_errors.assert_error_equals(tilia.errors.RELOAD_FROM_FILE_FAILED_BEAT_TL_DELETED)

    def test_reload_by_measure_another_beat_tl_deleted(self, tluis, actions, tilia_errors, marker_tlui, beat_tlui, tilia_state):
        beat_tlui.timeline.beat_pattern = [1]
        for i in range(4):
            tilia_state.current_time = i
            actions.trigger(TiliaAction.BEAT_ADD)

        # create another beat timeline
        with Serve(Get.FROM_USER_STRING, ('', True)):
            with Serve(Get.FROM_USER_BEAT_PATTERN, (True, [1])):
                actions.trigger(TiliaAction.TIMELINES_ADD_BEAT_TIMELINE)

        data1 = 'measure\n1\n2\n3'

        # import from csv
        with PatchImportFromCSV(marker_tlui, 'measure', data1, beat_tlui=beat_tlui):
            actions.trigger(TiliaAction.MARKER_IMPORT_FROM_CSV)

        # delete beat timeline not used for import
        with Serve(Get.CONTEXT_MENU_TIMELINE_UI, [tluis[2]]):
            with Serve(Get.FROM_USER_YES_OR_NO, (True, True)):
                post(Post.TIMELINE_DELETE_FROM_CONTEXT_MENU)

        data2 = 'measure\n1\n2\n3\n4'
        # reload from file with different data
        with Serve(Get.CONTEXT_MENU_TIMELINE_UI, [marker_tlui]):
            with patch('builtins.open', mock_open(read_data=data2)):
                actions.trigger(TiliaAction.TIMELINE_RELOAD_FROM_FILE)

        assert len(marker_tlui) == 4

    def test_reload_by_time(self, actions, marker_tlui):
        data1 = 'time\n1\n2\n3'
        data2 = 'time\n1\n2\n3\n4'
        self._reload_from_csv(actions, marker_tlui, 'time', data1, data2)
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

    def test_reload_file_not_found(self, actions, marker_tlui, tilia_errors):
        data = 'time\n1\n2\n3'
        self._reload_with_error(actions, marker_tlui, data, FileNotFoundError)
        tilia_errors.assert_error_equals(tilia.errors.CSV_FILE_NOT_FOUND)

    def test_reload_permission_denied(self, actions, marker_tlui, tilia_errors):
        data = 'time\n1\n2\n3'
        self._reload_with_error(actions, marker_tlui, data, PermissionError)
        tilia_errors.assert_error_equals(tilia.errors.CSV_PERMISSION_DENIED)

    def test_reload_import_failed(self, actions, marker_tlui, tilia_errors):
        data = 'time\n1\n2\n3'
        self._reload_with_error(actions, marker_tlui, data, ValueError)
        tilia_errors.assert_in_error_title(tilia.errors.CSV_IMPORT_FAILED.title)
        tilia_errors.assert_in_error_message('ValueError')
