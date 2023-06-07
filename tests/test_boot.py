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

    def test_get_initial_file_path_good_path(self):
        path = str(Path(__file__).parent / "test_file.tla")
        assert Path(get_initial_file(path)) == Path(path)


class TestGetSetupParser:
    def test_setup_parser_default_values(self):
        sys.argv = ["main.py"]

        args = setup_parser()

        assert args.logging == "INFO"
        assert args.file == ""
        assert args.user_interface == "tk"

    def test_setup_parser_custom_values(self):
        sys.argv = [
            "script.py",
            "--logging",
            "DEBUG",
            "input.txt",
            "--user-interface",
            "cli",
        ]

        args = setup_parser()

        assert args.logging == "DEBUG"
        assert args.file == "input.txt"
        assert args.user_interface == "cli"

    def test_setup_parser_invalid_logging_choice(self):
        sys.argv = ["main.py", "--logging", "INVALID"]

        with pytest.raises(argparse.ArgumentError):
            setup_parser()

    def test_setup_parser_logging_choice(self):
        sys.argv = ["main.py", "--logging", "WARNING"]

        args = setup_parser()

        assert args.logging == "WARNING"

    def test_setup_parser_user_interface_cli(self):
        sys.argv = ["main.py", "--user-interface", "cli"]

        args = setup_parser()

        assert args.user_interface == "cli"

    def test_setup_parser_invalid_user_interface_choice(self):
        sys.argv = ["main.py", "--user-interface", "INVALID"]

        with pytest.raises(argparse.ArgumentError):
            setup_parser()
