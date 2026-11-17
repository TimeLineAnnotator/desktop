import argparse
from unittest import mock
from unittest.mock import patch

import pytest

from tilia.timelines.marker.timeline import MarkerTimeline


class TestCLI:
    def test_wrong_argument(self, cli, tilia_errors):
        cli.parse_and_run("nonsense")

        tilia_errors.assert_error()
        tilia_errors.assert_in_error_message("nonsense")

    PARSE_COMMAND_CASES = [
        ("spaced args", ["spaced", "args"]),
        ('"spaced args"', ["spaced args"]),
        ('"spaced args" and more', ["spaced args", "and", "more"]),
        ('"three spaced args"', ["three spaced args"]),
        ('"three spaced args" and more', ["three spaced args", "and", "more"]),
        (
            'surrounded "quoted args" surrounded',
            ["surrounded", "quoted args", "surrounded"],
        ),
        ('"unfinished', None),
        ('"unfinished and more', None),
        ('not started"', None),
        ('notstarted"', None),
        ('notstarted" and more', None),
        ('this has notstarted"', None),
        ('"onestring"', ["onestring"]),
        ("trailing space ", ["trailing", "space"]),
        ("trailing spaces     ", ["trailing", "spaces"]),
    ]

    @pytest.mark.parametrize("command,result", PARSE_COMMAND_CASES)
    def test_parse_command(self, cli, command, result):

        assert cli.parse_command(command) == result

    @pytest.mark.parametrize("command", ["quit", "exit", "q"])
    def test_quit_command_stops_loop(self, cli, command):
        cli._is_running = True
        cli.parse_and_run(command)
        assert not cli._is_running

    def test_launch_eof_sets_is_running_false(self, cli):
        with mock.patch("builtins.input", side_effect=EOFError):
            with pytest.raises(SystemExit):
                cli.launch()
        assert not cli._is_running

    @staticmethod
    def names_in_the_document(tilia):
        return {tl.name for tl in tilia.file_manager.file.document.timelines.values()}

    def test_a_command_s_edit_reaches_the_document_at_once(self, cli, tilia):
        # A command records nothing for undo, so its end is where the document
        # follows TiLiA (TimeLineAnnotator/project-management#449).
        cli.parse_and_run('timelines add marker --name "Added"')

        assert "Added" in self.names_in_the_document(tilia)

    def test_so_does_what_a_failed_command_did(self, cli, tilia):
        def add_then_fail(_):
            tilia.timelines.create_timeline(MarkerTimeline, name="Half done")
            raise RuntimeError("the command failed")

        namespace = argparse.Namespace(func=add_then_fail)
        with patch.object(cli.parser, "parse_args", return_value=namespace):
            assert cli.run(["anything"])

        assert "Half done" in self.names_in_the_document(tilia)
