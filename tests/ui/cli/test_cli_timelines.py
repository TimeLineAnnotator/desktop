from tilia.timelines.timeline_kinds import TimelineKind

from unittest.mock import patch


class TestTimelineAdd:
    def test_add_hierarchy_timeline(self, tls, cli):
        cli.run(['timeline', 'add', 'hrc', '--name', 'test'])

        tl = tls.get_timelines()[0]
        assert tl.KIND == TimelineKind.HIERARCHY_TIMELINE
        assert tl.name == 'test'

    def test_add_marker_timeline(self, tls, cli):
        cli.run(['timeline', 'add', 'mrk', '--name', 'test'])

        tl = tls.get_timelines()[0]
        assert tl.KIND == TimelineKind.MARKER_TIMELINE
        assert tl.name == 'test'


class TestTimelineList:
    def test_list_timelines_no_timelines(self, tls, cli):
        with patch('builtins.print') as mock_print:
            cli.run(['timeline', 'list'])

            printed = mock_print.call_args[0][0]

            assert 'name' in printed
            assert 'id' in printed
            assert 'kind' in printed
            assert '0' not in printed

    def test_list_timelines_single_timeline(self, tls, cli):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE, name='test1')

        tl = tls.get_timelines()[0]
        with patch('builtins.print') as mock_print:
            cli.run(['timeline', 'list'])

            printed = mock_print.call_args[0][0]

            assert 'test1' in printed
            assert 'Hierarchy' in printed
            assert tl.id in printed

    def test_list_timelines_multiple_timelines(self, tls, cli):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE, name='test1')
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE, name='test2')
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE, name='test3')

        tl = tls.get_timelines()[0]
        with patch('builtins.print') as mock_print:
            cli.run(['timeline', 'list'])

            printed = mock_print.call_args[0][0]

            assert 'test1' in printed
            assert 'test2' in printed
            assert 'test3' in printed