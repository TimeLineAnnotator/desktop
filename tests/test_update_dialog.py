from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication, QProgressDialog

from tests.mock import patch_yes_or_no_dialog
from tilia.ui.dialogs import update as update_dialog

# Arbitrary: the dialog only renders this as label text. It is never compared
# to the app version, so no real version can outgrow it.
TARGET_VERSION = "1.2.3"


class _SyncThread:
    """Runs the target in the calling thread, so the update applies inline."""

    def __init__(self, target, daemon=None):
        self._target = target

    def start(self):
        self._target()


def _fake_update() -> MagicMock:
    update = MagicMock()
    update.TargetFullRelease.Version = TARGET_VERSION
    return update


def _progress_dialogs() -> list[QProgressDialog]:
    return [w for w in QApplication.topLevelWidgets() if isinstance(w, QProgressDialog)]


def _run_update(manager, update, monkeypatch) -> list[QProgressDialog]:
    monkeypatch.setattr(update_dialog.threading, "Thread", _SyncThread)
    with patch_yes_or_no_dialog(True):
        update_dialog.show_update_dialog(manager, update)
    QApplication.processEvents()
    return _progress_dialogs()


def _close(dialogs: list[QProgressDialog]) -> None:
    for dialog in dialogs:
        dialog.close()
        dialog.deleteLater()


def test_velopack_update_shows_download_progress(qtui, monkeypatch):
    manager = MagicMock()
    labels_while_downloading = []

    def download(_update, callback):
        labels_while_downloading.append(_progress_dialogs()[0].labelText())
        callback(42)

    manager.download_updates.side_effect = download
    update = _fake_update()

    dialogs = _run_update(manager, update, monkeypatch)

    try:
        assert len(dialogs) == 1
        assert dialogs[0].isVisible()
        assert dialogs[0].value() == 42
        assert TARGET_VERSION in labels_while_downloading[0]
        assert "Restarting" in dialogs[0].labelText()
        manager.apply_updates_and_restart.assert_called_once_with(update)
    finally:
        _close(dialogs)


def test_velopack_update_closes_progress_on_failure(qtui, monkeypatch):
    manager = MagicMock()
    manager.download_updates.side_effect = RuntimeError("network down")
    update = _fake_update()
    shown_errors = []
    monkeypatch.setattr(
        update_dialog.tilia.errors, "display", lambda *args: shown_errors.append(args)
    )

    dialogs = _run_update(manager, update, monkeypatch)

    try:
        assert not any(dialog.isVisible() for dialog in dialogs)
        assert shown_errors
        assert shown_errors[0][1] == "network down"
        manager.apply_updates_and_restart.assert_not_called()
    finally:
        _close(dialogs)
