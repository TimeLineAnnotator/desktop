import argparse
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtGui import QFileOpenEvent

from tilia.boot import PendingFileOpen, TiliaApplication, get_initial_file, setup_parser


class TestGetInitialFilePath:
    def test_get_initial_file_no_file(self):
        assert get_initial_file("", MagicMock()) == ""

    def test_get_initial_file_path_does_not_exist(self):
        error = MagicMock()
        get_initial_file("inexistent.tla", error)
        error.assert_called_once()

    def test_get_initial_file_path_with_non_tla_extension(self):
        error = MagicMock()
        get_initial_file(str(Path(__file__)), error)
        error.assert_called_once()

    def test_get_initial_file_path_good_path(self, tmp_path):
        file_path = tmp_path / "test.tla"
        file_path.touch()
        error = MagicMock()
        result = get_initial_file(str(file_path.resolve()), error)
        assert Path(result) == Path(file_path)
        error.assert_not_called()

    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows-specific")
    def test_accepts_backslash(self, tmp_path):
        file_path = tmp_path / "test.tla"
        file_path.touch()
        win_path = str(file_path)  # on Windows, str(Path) uses backslashes
        assert "\\" in win_path
        error = MagicMock()
        assert get_initial_file(win_path, error) == win_path
        error.assert_not_called()


class TestGetSetupParser:
    def test_setup_parser_default_values(self):
        sys.argv = ["main.py"]

        args = setup_parser()

        assert args.file == ""
        assert args.user_interface == "qt"

    def test_setup_parser_custom_values(self, tmp_path):
        file_path = tmp_path / "test.tla"
        file_path.touch()
        posix_path = file_path.as_posix()

        sys.argv = ["script.py", posix_path, "--user-interface", "cli"]

        args = setup_parser()

        assert args.file == posix_path
        assert args.user_interface == "cli"

    def test_setup_parser_user_interface_cli(self):
        sys.argv = ["main.py", "--user-interface", "cli"]

        args = setup_parser()

        assert args.file == ""
        assert args.user_interface == "cli"

    def test_setup_parser_invalid_user_interface_choice(self):
        sys.argv = ["main.py", "--user-interface", "INVALID"]

        with pytest.raises(argparse.ArgumentError):
            setup_parser()

    def test_setup_parser_file_after_interface_flag(self, tmp_path):
        file_path = tmp_path / "test.tla"
        file_path.touch()
        posix_path = file_path.as_posix()

        sys.argv = ["main.py", "--user-interface", "cli", posix_path]

        args = setup_parser()

        assert args.file == posix_path
        assert args.user_interface == "cli"

    def test_setup_parser_nonexistent_file_raises(self):
        sys.argv = ["main.py", "nonexistent.tla"]

        with pytest.raises(SystemExit):
            setup_parser()

    def test_setup_parser_wrong_extension_raises(self, tmp_path):
        file_path = tmp_path / "test.txt"
        file_path.touch()

        sys.argv = ["main.py", file_path.as_posix()]

        with pytest.raises(SystemExit):
            setup_parser()

    @pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows-specific")
    def test_setup_parser_accepts_backslash(self, tmp_path):
        file_path = tmp_path / "test.tla"
        file_path.touch()
        win_path = str(file_path)  # on Windows, str(Path) uses backslashes
        sys.argv = ["tilia.exe", win_path]

        args = setup_parser()

        assert args.file == win_path


class TestPendingFileOpen:
    """PendingFileOpen backs TiliaApplication's QFileOpenEvent handling (used
    for macOS "open with"/double-click launches, which arrive as an event
    rather than in argv). Split out and tested standalone because only one
    QApplication may exist per process, and the session already owns it.
    """

    def test_buffers_path_until_callback_is_set(self):
        pending = PendingFileOpen()
        pending.handle("/tmp/probe.tla")

        received = []
        pending.set_callback(received.append)

        assert received == ["/tmp/probe.tla"]

    def test_delivers_immediately_once_callback_is_already_set(self):
        pending = PendingFileOpen()
        received = []
        pending.set_callback(received.append)

        pending.handle("/tmp/probe.tla")

        assert received == ["/tmp/probe.tla"]

    def test_does_not_redeliver_an_already_consumed_path(self):
        pending = PendingFileOpen()
        pending.handle("/tmp/probe.tla")
        first, second = [], []
        pending.set_callback(first.append)
        pending.set_callback(second.append)

        assert first == ["/tmp/probe.tla"]
        assert second == []

    def test_no_path_and_no_callback_is_a_no_op(self):
        pending = PendingFileOpen()
        pending.set_callback(lambda path: pytest.fail("should not be called"))


class TestTiliaApplicationFileOpenEvent:
    def test_file_open_event_is_consumed_and_routed(self, qapplication):
        # Only one QApplication may exist per process, and the session-scoped
        # qapplication fixture already owns it — even TiliaApplication.__new__
        # trips PySide6's singleton check, so this reaches into the live
        # instance's class instead of constructing a second one.
        instance = qapplication
        instance._file_open = PendingFileOpen()
        received = []
        TiliaApplication.set_file_open_callback(instance, received.append)
        event = MagicMock(spec=QFileOpenEvent)
        event.type.return_value = QEvent.Type.FileOpen
        event.file.return_value = "/tmp/probe.tla"

        handled = TiliaApplication.event(instance, event)

        assert handled is True
        assert received == ["/tmp/probe.tla"]
