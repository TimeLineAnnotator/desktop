from tests.constants import EXAMPLE_MEDIA_PATH
from tilia.timelines.timeline_kinds import TimelineKind


class TestTimelineAdd:
    def test_add_timeline_with_no_duration_fails(self, cli, tls, tilia_state, tilia_errors):
        tilia_state.duration = 0
        cli.parse_and_run("timeline add mrk")

        assert len(tls) == 0
        tilia_errors.assert_error()

    def test_retry_add_timeline_after_loading_media(self, cli, tls, tilia_state, tilia_errors):
        tilia_state.duration = 0
        cli.parse_and_run("timeline add mrk")
        cli.parse_and_run("load-media " + EXAMPLE_MEDIA_PATH)
        cli.parse_and_run("timeline add mrk")

        assert len(tls) == 1

    def test_retry_add_timeline_after_setting_duration(self, cli, tls, tilia_state, tilia_errors):
        tilia_state.duration = 0
        cli.parse_and_run("timeline add mrk")
        cli.parse_and_run("metadata set-media-length 10")
        cli.parse_and_run("timeline add mrk")

        assert len(tls) == 1

    def test_add_hierarchy_timeline(self, cli, tls):
        cli.parse_and_run("timeline add hrc --name test")

        tl = tls.get_timelines()[0]
        assert tl.KIND == TimelineKind.HIERARCHY_TIMELINE
        assert tl.name == "test"

    def test_add_marker_timeline(self, cli, tls):
        cli.parse_and_run("timeline add mrk --name test")

        tl = tls.get_timelines()[0]
        assert tl.KIND == TimelineKind.MARKER_TIMELINE
        assert tl.name == "test"

    def test_add_beat_timeline(self, cli, tls):
        cli.parse_and_run("timeline add beat --name test --beat-pattern 1 2 3")

        tl = tls.get_timelines()[0]
        assert tl.KIND == TimelineKind.BEAT_TIMELINE
        assert tl.name == "test"
        assert tl.beat_pattern == [1, 2, 3]

    def test_add_beat_timeline_no_beat_pattern_provided(self, cli, tls):
        cli.parse_and_run("timeline add beat")

        tl = tls.get_timelines()[0]
        assert tl.beat_pattern == [4]
