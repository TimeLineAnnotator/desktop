from unittest.mock import patch

from tests.mock import Serve
from tests.ui.cli.common import cli_run
from tilia.requests import Get
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.actions import TiliaAction


class TestTimelineList:
    def test_list_timelines_no_timelines(self):
        with patch("builtins.print") as mock_print:
            cli_run('timeline list')

            printed = mock_print.call_args[0][0]

            assert "name" in printed
            assert "ord" in printed
            assert "kind" in printed
            assert "1" not in printed

    def test_list_timelines_single_timeline(self, hierarchy_tl, actions):
        hierarchy_tl.set_data('name', 'test1')

        with patch("builtins.print") as mock_print:
            cli_run('timeline list')

            printed = mock_print.call_args[0][0]

            assert "test1" in printed
            assert "Hierarchy" in printed
            assert str(hierarchy_tl.ordinal) in printed

    def test_list_timelines_multiple_timelines(self, tls, actions):
        for name in ["test1", "test2", "test3"]:
            with Serve(Get.FROM_USER_STRING, (name, True)):
                actions.trigger(TiliaAction.TIMELINES_ADD_HIERARCHY_TIMELINE)

        with patch("builtins.print") as mock_print:
            cli_run('timelines list')

            printed = mock_print.call_args[0][0]

            assert "test1" in printed
            assert "test2" in printed
            assert "test3" in printed


class TestTimelineRemove:
    def test_type_not_provided(self, hierarchy_tl, tls):
        cli_run('timeline remove')

        assert not tls.is_empty

    def test_by_name_one_timeline(self, tls, actions):
        with Serve(Get.FROM_USER_STRING, ("test", True)):
            actions.trigger(TiliaAction.TIMELINES_ADD_HIERARCHY_TIMELINE)

        cli_run('timeline remove name test')

        assert tls.is_empty

    def test_remove_by_name_multiple_timelines(self, actions, tls):
        for name in ["test1", "test2", "test3"]:
            with Serve(Get.FROM_USER_STRING, (name, True)):
                actions.trigger(TiliaAction.TIMELINES_ADD_HIERARCHY_TIMELINE)

        cli_run('timeline remove name test1')

        assert len(tls) == 2

        cli_run('timeline remove name test2')

        assert len(tls) == 1

    def test_remove_by_name_not_found(self, tls, actions):
        with Serve(Get.FROM_USER_STRING, ("test", True)):
            actions.trigger(TiliaAction.TIMELINES_ADD_HIERARCHY_TIMELINE)

        with patch("builtins.print") as mock_print:
            cli_run('timeline remove name othername')

            printed = mock_print.call_args[0][0]
            assert "No timeline found" in printed
            assert "othername" in printed

    def test_remove_by_name_when_no_timelines(self):
        with patch("builtins.print") as mock_print:
            cli_run('timeline remove name test')

            printed = mock_print.call_args[0][0]
            assert "No timeline found" in printed
            assert "test" in printed

    def test_remove_by_name_name_not_provide(self, tls, hierarchy_tl):
        cli_run('timeline remove name')

        assert not tls.is_empty

    def test_remove_by_ordinal_one_timeline(self, tls, hierarchy_tl):
        cli_run('timeline remove ordinal 1')

        assert len(tls) == 0

    def test_remove_by_ordinal_multiple_timelines(self, actions, tls):
        for i in range(3):
            with Serve(Get.FROM_USER_STRING, ("", True)):
                actions.trigger(TiliaAction.TIMELINES_ADD_HIERARCHY_TIMELINE)

        cli_run('timeline remove ordinal 1')

        assert len(tls) == 2

        cli_run('timeline remove ordinal 2')

        assert len(tls) == 1

    def test_remove_by_ordinal_not_found(self, tls):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)

        with patch("builtins.print") as mock_print:
            cli_run('timeline remove ordinal 3')

            printed = mock_print.call_args[0][0]
            assert "No timeline found" in printed
            assert "3" in printed

    def test_remove_by_ordinal_when_no_timelines(self, tls):
        with patch("builtins.print") as mock_print:
            cli_run('timeline remove ordinal 1')

            printed = mock_print.call_args[0][0]
            assert "No timeline found" in printed
            assert "1" in printed

    def test_remove_by_ordinal_ordinal_not_provided(self, tls, hierarchy_tl):
        cli_run('timeline remove ordinal')

        assert not tls.is_empty
