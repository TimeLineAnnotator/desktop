from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.windows.manage_timelines import ManageTimelines


class TestChangeTimelineOrder:
    def test_increase_ordinal(self, tls):
        tls.create_timeline(TimelineKind.MARKER_TIMELINE, name='first')
        tls.create_timeline(TimelineKind.MARKER_TIMELINE, name='second')
        tls.create_timeline(TimelineKind.MARKER_TIMELINE, name='third')

        mt = ManageTimelines()
        mt.list_widget.setCurrentRow(1)
        mt.up_button.click()

        assert tls[0].get_data('name') == 'second'
        assert tls[1].get_data('name') == 'first'
        assert tls[2].get_data('name') == 'third'

    def test_increase_ordinal_with_first_selected_does_nothing(self, tls):
        tls.create_timeline(TimelineKind.MARKER_TIMELINE, name='first')
        tls.create_timeline(TimelineKind.MARKER_TIMELINE, name='second')
        tls.create_timeline(TimelineKind.MARKER_TIMELINE, name='third')

        mt = ManageTimelines()
        mt.list_widget.setCurrentRow(0)
        mt.up_button.click()

        assert tls[0].get_data('name') == 'first'
        assert tls[1].get_data('name') == 'second'
        assert tls[2].get_data('name') == 'third'

    def test_decrease_ordinal(self, tls):
        tls.create_timeline(TimelineKind.MARKER_TIMELINE, name='first')
        tls.create_timeline(TimelineKind.MARKER_TIMELINE, name='second')
        tls.create_timeline(TimelineKind.MARKER_TIMELINE, name='third')

        mt = ManageTimelines()
        mt.list_widget.setCurrentRow(0)
        mt.down_button.click()

        assert tls[0].get_data('name') == 'second'
        assert tls[1].get_data('name') == 'first'
        assert tls[2].get_data('name') == 'third'

    def test_decrease_ordinal_with_last_selected_does_nothing(self, tls):
        tls.create_timeline(TimelineKind.MARKER_TIMELINE, name='first')
        tls.create_timeline(TimelineKind.MARKER_TIMELINE, name='second')
        tls.create_timeline(TimelineKind.MARKER_TIMELINE, name='third')

        mt = ManageTimelines()
        mt.list_widget.setCurrentRow(2)
        mt.down_button.click()

        assert tls[0].get_data('name') == 'first'
        assert tls[1].get_data('name') == 'second'
        assert tls[2].get_data('name') == 'third'
