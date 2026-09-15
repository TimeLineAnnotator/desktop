from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication, QProgressDialog

from tests.mock import Serve
from tilia.requests import Get
from tilia.ui.dialogs import update as update_dialog


class _SyncThread:
    def __init__(self, target, daemon=None):
        self._target = target

    def start(self):
        self._target()


def _progress_dialogs() -> list[QProgressDialog]:
    return [w for w in QApplication.topLevelWidgets() if isinstance(w, QProgressDialog)]


def test_velopack_update_shows_download_progress(qtui, monkeypatch):
    manager = MagicMock()
    manager.download_updates.side_effect = lambda _update, callback: callback(42)
    update = MagicMock()
    update.TargetFullRelease.Version = "89.9.9"
    monkeypatch.setattr(update_dialog.threading, "Thread", _SyncThread)

    with Serve(Get.FROM_USER_YES_OR_NO, True):
        update_dialog.show_update_dialog(manager, update)
    QApplication.processEvents()

    dialogs = _progress_dialogs()
    try:
        assert len(dialogs) == 1
        assert dialogs[0].isVisible()
        assert dialogs[0].value() == 42
        manager.apply_updates_and_restart.assert_called_once_with(update)
    finally:
        for dialog in dialogs:
            dialog.close()
            dialog.deleteLater()


def test_velopack_update_closes_progress_on_failure(qtui, monkeypatch):
    manager = MagicMock()
    manager.download_updates.side_effect = RuntimeError("network down")
    update = MagicMock()
    update.TargetFullRelease.Version = "89.9.9"
    monkeypatch.setattr(update_dialog.threading, "Thread", _SyncThread)
    shown_errors = []
    monkeypatch.setattr(
        update_dialog.tilia.errors, "display", lambda *args: shown_errors.append(args)
    )

    with Serve(Get.FROM_USER_YES_OR_NO, True):
        update_dialog.show_update_dialog(manager, update)
    QApplication.processEvents()

    dialogs = _progress_dialogs()
    try:
        assert not any(dialog.isVisible() for dialog in dialogs)
        assert shown_errors
        assert shown_errors[0][1] == "network down"
        manager.apply_updates_and_restart.assert_not_called()
    finally:
        for dialog in dialogs:
            dialog.deleteLater()
