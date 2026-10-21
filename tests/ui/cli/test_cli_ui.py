from unittest import mock

import pytest

from tilia.requests import Post, post
from tilia.ui.cli import io
from tilia.ui.cli.ui import CLI


@pytest.fixture
def non_interactive_cli():
    _cli = CLI(interactive=False)
    yield _cli
    io.set_interactive(True)


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


class TestRunNonInteractive:
    def test_commands_separated_by_semicolons(self, non_interactive_cli, tls):
        code = non_interactive_cli.run_non_interactive(
            "timelines add hierarchy --name a;timelines add hierarchy --name b"
        )

        assert code == 0
        assert [tl.get_data("name") for tl in tls] == ["a", "b"]

    def test_commands_separated_by_newlines(self, non_interactive_cli, tls):
        code = non_interactive_cli.run_non_interactive(
            "timelines add hierarchy\ntimelines add hierarchy"
        )

        assert code == 0
        assert len(tls) == 2

    def test_semicolon_inside_quotes(self, non_interactive_cli, tls):
        code = non_interactive_cli.run_non_interactive(
            'timelines add hierarchy --name "a;b"'
        )

        assert code == 0
        assert tls[0].get_data("name") == "a;b"

    def test_no_commands(self, non_interactive_cli):
        assert non_interactive_cli.run_non_interactive("") == 0

    def test_stops_at_first_failing_command(self, non_interactive_cli, tls):
        code = non_interactive_cli.run_non_interactive(
            "nonsense;timelines add hierarchy"
        )

        assert code == 1
        assert len(tls) == 0

    def test_fails_instead_of_asking_for_input(
        self, non_interactive_cli, tls, tilia_errors
    ):
        # Clearing a modified file asks for confirmation.
        with mock.patch("builtins.input") as input_mock:
            code = non_interactive_cli.run_non_interactive(
                "timelines add hierarchy;clear"
            )

        assert code == 1
        input_mock.assert_not_called()
        tilia_errors.assert_in_error_message("Input required")
        assert len(tls) == 1

    def test_fails_if_error_was_displayed_before(self, non_interactive_cli, tls):
        # E.g. when the file given on the command line could not be opened.
        post(Post.DISPLAY_ERROR, "Error", "Something went wrong.")

        code = non_interactive_cli.run_non_interactive("timelines add hierarchy")

        assert code == 1
        assert len(tls) == 0
