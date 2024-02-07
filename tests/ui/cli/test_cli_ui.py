from tilia.requests.post import stop_listening_to_all
from tilia.ui.cli.ui import CLI

from unittest.mock import patch


class TestCLI:
    def test_constructor(self):
        cli = CLI()
        stop_listening_to_all(cli)

    def test_wrong_argument(self, cli):
        args = ["nonsense"]
        with patch("builtins.print") as mock_print:
            cli.run(args)
            mock_print.assert_called_once()
            assert "nonsense" in mock_print.call_args[0][0]
            assert "invalid choice" in mock_print.call_args[0][0]
