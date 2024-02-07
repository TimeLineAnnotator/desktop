from unittest.mock import patch

from tilia.timelines.timeline_kinds import TimelineKind


class TestTimelineList:
    def test_list_timelines_no_timelines(self, tls, cli):
        with patch("builtins.print") as mock_print:
            cli.run(["timeline", "list"])

            printed = mock_print.call_args[0][0]

            assert "name" in printed
            assert "ord" in printed
            assert "kind" in printed
            assert "1" not in printed

    def test_list_timelines_single_timeline(self, tls, cli):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE, name="test1")

        tl = tls.get_timelines()[0]
        with patch("builtins.print") as mock_print:
            cli.run(["timeline", "list"])

            printed = mock_print.call_args[0][0]

            assert "test1" in printed
            assert "Hierarchy" in printed
            assert str(tl.ordinal) in printed

    def test_list_timelines_multiple_timelines(self, tls, cli):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE, name="test1")
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE, name="test2")
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE, name="test3")

        _ = tls.get_timelines()[0]
        with patch("builtins.print") as mock_print:
            cli.run(["timeline", "list"])

            printed = mock_print.call_args[0][0]

            assert "test1" in printed
            assert "test2" in printed
            assert "test3" in printed


class TestTimelineRemove:
    def test_remove_type_not_provide(self, tls, cli):
        cli.run(["timeline", "remove"])

        assert type(cli.exception) == SystemExit

    def test_remove_by_name_one_timeline(self, tls, cli):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE, name="test1")

        cli.run(["timeline", "remove", "name", "test1"])

        assert len(tls) == 0

    def test_remove_by_name_multiple_timelines(self, tls, cli):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE, name="test1")
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE, name="test2")
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE, name="test3")

        cli.run(["timeline", "remove", "name", "test1"])

        assert len(tls) == 2

        cli.run(["timeline", "remove", "name", "test3"])

        assert len(tls) == 1

    def test_remove_by_name_not_found(self, tls, cli):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE, name="test1")

        with patch("builtins.print") as mock_print:
            cli.run(["timeline", "remove", "name", "othername"])

            printed = mock_print.call_args[0][0]
            assert "No timeline found" in printed
            assert "othername" in printed
        assert type(cli.exception) == ValueError

    def test_remove_by_name_when_no_timelines(self, tls, cli):
        with patch("builtins.print") as mock_print:
            cli.run(["timeline", "remove", "name", "test"])

            printed = mock_print.call_args[0][0]
            assert "No timeline found" in printed
            assert "test" in printed

    def test_remove_by_name_name_not_provide(self, tls, cli):
        cli.run(["timeline", "remove", "name"])

        assert type(cli.exception) == SystemExit

    def test_remove_by_ordinal_one_timeline(self, tls, cli):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE, name="test1")

        cli.run(["timeline", "remove", "ordinal", "1"])

        assert len(tls) == 0

    def test_remove_by_ordinal_multiple_timelines(self, tls, cli):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)

        cli.run(["timeline", "remove", "ordinal", "1"])

        assert len(tls) == 2

        cli.run(["timeline", "remove", "ordinal", "1"])

        assert len(tls) == 1

    def test_remove_by_ordinal_not_found(self, tls, cli):
        tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)

        with patch("builtins.print") as mock_print:
            cli.run(["timeline", "remove", "ordinal", "3"])

            printed = mock_print.call_args[0][0]
            assert "No timeline found" in printed
            assert "3" in printed
        assert type(cli.exception) == ValueError

    def test_remove_by_ordinal_when_no_timelines(self, tls, cli):
        with patch("builtins.print") as mock_print:
            cli.run(["timeline", "remove", "ordinal", "1"])

            printed = mock_print.call_args[0][0]
            assert "No timeline found" in printed
            assert "1" in printed

    def test_remove_by_ordinal_ordinal_not_provide(self, tls, cli):
        cli.run(["timeline", "remove", "ordinal"])

        assert type(cli.exception) == SystemExit
