from unittest.mock import patch

import pytest

from tilia.ui.cli.io import ask_yes_or_no
from tilia.ui.cli.ui import on_ask_retry_media_file, on_ask_retry_pdf_file


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
        ],
    )
    def test_ask_yes_or_no(self, user_input, expected, count):
        with patch("builtins.input", side_effect=user_input) as q:
            assert ask_yes_or_no("Some prompt") == expected
        assert q.call_count == count

    @pytest.mark.parametrize(
        "kwargs,option",
        [({}, "Yes/no"), ({"default": True}, "Yes/no"), ({"default": False}, "yes/No")],
    )
    def test_default_value(self, kwargs, option):
        with patch("builtins.input", return_value="") as p:
            assert ask_yes_or_no("Some prompt", **kwargs) == kwargs.get("default", True)
        assert option in p.call_args.args[0]


class TestRetryHandlers:
    def test_on_ask_retry_media_file_returns_true_on_yes(self):
        with patch("builtins.input", return_value="y"):
            assert on_ask_retry_media_file() is True

    def test_on_ask_retry_media_file_returns_false_on_no(self):
        with patch("builtins.input", return_value="n"):
            assert on_ask_retry_media_file() is False

    def test_on_ask_retry_pdf_file_returns_true_on_yes(self):
        with patch("builtins.input", return_value="y"):
            assert on_ask_retry_pdf_file() is True

    def test_on_ask_retry_pdf_file_returns_false_on_no(self):
        with patch("builtins.input", return_value="n"):
            assert on_ask_retry_pdf_file() is False
