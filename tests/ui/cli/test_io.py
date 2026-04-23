from unittest.mock import patch

import pytest

from tilia.ui.cli.io import ask_yes_or_no


class TestInput:
    @pytest.mark.parametrize(
        "user_input,expected,count",
        [
            ("y", True, 1),
            ("Y", True, 1),
            ("yes", True, 1),
            ("YES", True, 1),
            ("Yes", True, 1),
            ("n", False, 1),
            ("N", False, 1),
            ("no", False, 1),
            ("NO", False, 1),
            (["anything", "no"], False, 2),
            ([""], True, 1),
        ],
    )
    def test_ask_yes_or_no(self, user_input, expected, count):
        with patch("builtins.input", side_effect=user_input) as q:
            assert ask_yes_or_no("Some prompt") == expected
        assert q.call_count == count
