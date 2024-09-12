import pytest

from tests.ui.cli.common import cli_run
from tilia.requests.post import stop_listening_to_all
from tilia.ui.cli.ui import CLI

from unittest.mock import patch


class TestCLI:
    def test_constructor(self):
        cli = CLI()
        stop_listening_to_all(cli)

    def test_wrong_argument(self):
        with patch("builtins.print") as mock_print:
            cli_run('nonsense')
            mock_print.assert_called_once()
            assert "nonsense" in mock_print.call_args[0][0]
            assert "invalid choice" in mock_print.call_args[0][0]

    PARSE_COMMAND_CASES = [
        ('spaced args', ['spaced', 'args']),
        ('"spaced args"', ['spaced args']),
        ('"spaced args" and more', ['spaced args', 'and', 'more']),
        ('"three spaced args"', ['three spaced args']),
        ('"three spaced args" and more', ['three spaced args', 'and', 'more']),
        ('surrounded "quoted args" surrounded', ['surrounded', 'quoted args', 'surrounded']),
        ('"unfinished', None),
        ('"unfinished and more', None),
        ('not started"', None),
        ('notstarted"', None),
        ('notstarted" and more', None),
        ('this has notstarted"', None),
        ('"onestring"', ['onestring'])
    ]

    @pytest.mark.parametrize("command,result", PARSE_COMMAND_CASES)
    def test_parse_command(self, command, result):
        assert CLI.parse_command(command) == result
