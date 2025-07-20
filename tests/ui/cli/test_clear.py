from io import StringIO

import pytest

from tilia.timelines.timeline_kinds import TimelineKind


class TestClear:
    @pytest.fixture(autouse=True)
    def setup_timelines(self, tls):
        tls.create_timeline(TimelineKind.SLIDER_TIMELINE)

    @staticmethod
    def assert_cleared(tls):
        assert len(tls) == 1
        assert tls[0].KIND == TimelineKind.SLIDER_TIMELINE

    def test_clear(self, cli, tls, tilia_state, user_actions):
        tilia_state.duration = 1
        cli.parse_and_run("timeline add hrc")
        cli.parse_and_run("clear --force")

        self.assert_cleared(tls)

    def test_clear_twice(self, cli, tls, tilia_state, user_actions):
        tilia_state.duration = 1
        cli.parse_and_run("timeline add hrc")
        cli.parse_and_run("clear --force")
        cli.parse_and_run("clear --force")

        self.assert_cleared(tls)

    def test_clear_saved_does_not_prompt_for_confirmation(
        self, cli, tls, tmp_path, tilia_state, user_actions
    ):
        tilia_state.duration = 1
        cli.parse_and_run("timeline add hrc")
        cli.parse_and_run("save " + str(tmp_path.resolve()))
        cli.parse_and_run("clear")

        self.assert_cleared(tls)

    def test_clear_unsaved_do_not_confirm(
        self, cli, tls, tmp_path, tilia_state, user_actions, monkeypatch
    ):
        tilia_state.duration = 1
        cli.parse_and_run("timeline add hrc")
        monkeypatch.setattr("sys.stdin", StringIO("no\n"))
        cli.parse_and_run("clear")

        assert len(tls) == 2

    def test_clear_unsaved_confirm(
        self, cli, tls, tmp_path, tilia_state, user_actions, monkeypatch
    ):
        tilia_state.duration = 1
        cli.parse_and_run("timeline add hrc")
        monkeypatch.setattr("sys.stdin", StringIO("yes\n"))
        cli.parse_and_run("clear")

        self.assert_cleared(tls)
