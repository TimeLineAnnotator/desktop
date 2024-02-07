from tilia.timelines.timeline_kinds import TimelineKind


class TestTimelineAdd:
    def test_add_hierarchy_timeline(self, tls, cli):
        cli.run(["timeline", "add", "hrc", "--name", "test"])

        tl = tls.get_timelines()[0]
        assert tl.KIND == TimelineKind.HIERARCHY_TIMELINE
        assert tl.name == "test"

    def test_add_marker_timeline(self, tls, cli):
        cli.run(["timeline", "add", "mrk", "--name", "test"])

        tl = tls.get_timelines()[0]
        assert tl.KIND == TimelineKind.MARKER_TIMELINE
        assert tl.name == "test"

    def test_add_beat_timeline(self, tls, cli):
        cli.run(
            [
                "timeline",
                "add",
                "beat",
                "--name",
                "test",
                "--beat-pattern",
                "1",
                "2",
                "3",
            ]
        )

        tl = tls.get_timelines()[0]
        assert tl.KIND == TimelineKind.BEAT_TIMELINE
        assert tl.name == "test"
        assert tl.beat_pattern == [1, 2, 3]

    def test_add_beat_timeline_no_beat_pattern_provided(self, tls, cli):
        cli.run(
            [
                "timeline",
                "add",
                "beat",
            ]
        )

        tl = tls.get_timelines()[0]
        assert tl.beat_pattern == [4]
