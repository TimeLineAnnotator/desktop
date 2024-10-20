import sys
from pathlib import Path
import argparse

import pytest

from tilia.boot import get_initial_file, setup_parser


class TestGetInitialFilePath:
    def test_get_initial_file_no_file(self):
        assert get_initial_file("") == ""

    def test_get_initial_file_path_does_not_exist(self):
        assert get_initial_file("inexistent.txt") == ""

    def test_get_initial_file_path_path_with_non_tla_extension(self):
        assert get_initial_file(str(Path(__file__))) == ""

    def test_get_initial_file_path_good_path(self, tmp_path):
        file_path = tmp_path / "test.tla"
        file_path.touch()
        assert Path(get_initial_file(str(file_path.resolve()))) == Path(file_path)


class TestGetSetupParser:
    def test_setup_parser_default_values(self):
        sys.argv = ["main.py"]

        args = setup_parser()

        assert args.file == ""
        assert args.user_interface == "qt"

    def test_setup_parser_custom_values(self):
        sys.argv = [
            "script.py",
            "input.txt",
            "--user-interface",
            "cli",
        ]

        args = setup_parser()

        assert args.file == "input.txt"
        assert args.user_interface == "cli"

    def test_setup_parser_user_interface_cli(self):
        sys.argv = ["main.py", "--user-interface", "cli"]

        args = setup_parser()

        assert args.user_interface == "cli"

    def test_setup_parser_invalid_user_interface_choice(self):
        sys.argv = ["main.py", "--user-interface", "INVALID"]

        with pytest.raises(argparse.ArgumentError):
            setup_parser()
