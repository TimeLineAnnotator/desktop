import pytest

from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.cli.timelines.collection import TimelineUICollection


@pytest.fixture
def cli_tlui_coll(cli):
    return TimelineUICollection(cli)

class TestTimelineUICOllection:

    def test_instantiate(self, cli_tlui_coll, cli):
        assert cli_tlui_coll.app_ui == cli

    def test_create_timeline_ui_hierarchy(self, cli_tlui_coll):
        hrc_tlui = cli_tlui_coll.create_timeline_ui(TimelineKind.HIERARCHY_TIMELINE, '123')

        assert hrc_tlui
        assert hrc_tlui.name == '123'
        assert len(cli_tlui_coll.timeline_uis) == 1
        assert hrc_tlui in cli_tlui_coll.timeline_uis

    def test_create_timeline_ui_marker(self, cli_tlui_coll):

        mrk_tlui = cli_tlui_coll.create_timeline_ui(TimelineKind.HIERARCHY_TIMELINE, '123')

        assert mrk_tlui
        assert mrk_tlui.name == '123'
        assert len(cli_tlui_coll.timeline_uis) == 1
        assert mrk_tlui in cli_tlui_coll.timeline_uis

    def test_create_timeline_ui_beat(self, cli_tlui_coll):
        beat_tlui = cli_tlui_coll.create_timeline_ui(TimelineKind.HIERARCHY_TIMELINE, '123')

        assert beat_tlui
        assert beat_tlui.name == '123'
        assert len(cli_tlui_coll.timeline_uis) == 1
        assert beat_tlui in cli_tlui_coll.timeline_uis

    def test_delete_timeline_ui_one_tlui(self, cli_tlui_coll):
        tlui = cli_tlui_coll.create_timeline_ui(TimelineKind.HIERARCHY_TIMELINE, '123')

        cli_tlui_coll.delete_timeline_ui(tlui)

        assert len(cli_tlui_coll.timeline_uis) == 0

    def test_delete_timeline_ui_two_tluis(self, cli_tlui_coll):
        tlui1 = cli_tlui_coll.create_timeline_ui(TimelineKind.HIERARCHY_TIMELINE, '123')
        tlui2 = cli_tlui_coll.create_timeline_ui(TimelineKind.HIERARCHY_TIMELINE, '123')

        cli_tlui_coll.delete_timeline_ui(tlui1)
        cli_tlui_coll.delete_timeline_ui(tlui2)

        assert len(cli_tlui_coll.timeline_uis) == 0

    def test_delete_timeline_ui_bad_arg(self, cli_tlui_coll):
        cli_tlui_coll.create_timeline_ui(TimelineKind.HIERARCHY_TIMELINE, '123')

        cli_tlui_coll.delete_timeline_ui('nonsense')

        assert len(cli_tlui_coll.timeline_uis) == 1

    def test_delete_timeline_ui_zero_tluis(self, cli_tlui_coll):
        cli_tlui_coll.delete_timeline_ui(None)

        assert len(cli_tlui_coll.timeline_uis) == 0
