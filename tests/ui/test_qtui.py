from unittest.mock import patch

from tests.mock import Serve
from tilia.requests import Get
from tilia.ui.actions import TiliaAction
from tilia.ui.windows import WindowKind


class TestCreateTimeline:
    def test_create(self, tls, hierarchy_tlui):
        assert not tls.is_empty

    def test_create_without_media_loaded(self, tilia, tls, user_actions):
        with Serve(Get.MEDIA_DURATION, 0):
            with Serve(Get.FROM_USER_STRING, ("", True)):
                user_actions.trigger(TiliaAction.TIMELINES_ADD_HIERARCHY_TIMELINE)

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
