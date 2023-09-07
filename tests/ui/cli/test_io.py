from unittest.mock import patch

import pytest

from tilia.ui.cli.io import ask_yes_or_no


class TestInput:
    @pytest.mark.parametrize(
        "user_input,expected",
        [
            ("y", True),
            ("Y", True),
            ("yes", True),
            ("YES", True),
            ("Yes", True),
            ("n", False),
            ("N", False),
            ("no", False),
            ("NO", False),
            ("anything", False),
            ("", False),
        ],
    )
    def test_ask_yes_or_no(self, user_input, expected):
        with patch("builtins.input", return_value=user_input):
            assert ask_yes_or_no("Some prompt") == expected
