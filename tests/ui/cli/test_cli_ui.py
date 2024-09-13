import pytest

from unittest.mock import patch


class TestCLI:
    def test_wrong_argument(self, cli):
        with patch("builtins.print") as mock_print:
            cli.parse_and_run('nonsense')
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
    def test_parse_command(self, cli, command, result):

        assert cli.parse_command(command) == result
