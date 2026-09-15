from __future__ import annotations

import os
import subprocess
import sys
import threading
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox, QProgressDialog

import tilia.constants
import tilia.errors
import tilia.updates
from tilia.requests import Get, get

if TYPE_CHECKING:
    from velopack import UpdateInfo, UpdateManager


def _display_information(title: str, message: str) -> None:
    QMessageBox.information(get(Get.MAIN_WINDOW), title, message)


def show_update_dialog(
    manager: UpdateManager | None,
    update: UpdateInfo | tilia.updates.GitUpdateInfo | None,
) -> None:
    if isinstance(update, tilia.updates.GitUpdateInfo):
        _show_git_dialog(update)
    else:
        _show_velopack_dialog(manager, update)


def _show_velopack_dialog(
    manager: UpdateManager | None, update: UpdateInfo | None
) -> None:
    if manager is None:
        _display_information(
            "Check for Updates",
            "TiLiA is running from source. Update checking is not available.",
        )
        return

    if update is None:
        _display_information("Check for Updates", "TiLiA is up to date.")
        return

    version = update.TargetFullRelease.Version
    if not get(
        Get.FROM_USER_YES_OR_NO,
        "Update Available",
        f"Version {version} is available. Restart and install now?",
    ):
        return

    parent = get(Get.MAIN_WINDOW)

    # The download can take minutes; without visible progress users assume
    # nothing happens and close TiLiA, which kills the daemon download thread.
    progress = QProgressDialog(f"Downloading TiLiA {version}...", "", 0, 100, parent)
    progress.setWindowTitle("Updating TiLiA")
    progress.setCancelButton(None)  # Velopack downloads cannot be cancelled
    progress.setWindowModality(Qt.WindowModality.ApplicationModal)
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.setValue(0)
    progress.show()

    def _on_progress(percent: int) -> None:
        QTimer.singleShot(0, progress, lambda: progress.setValue(percent))

    def _apply():
        try:
            manager.download_updates(update, _on_progress)
            QTimer.singleShot(
                0, progress, lambda: progress.setLabelText("Restarting TiLiA...")
            )
            manager.apply_updates_and_restart(update)
        except Exception as e:
            msg = str(e)

            def _show_error() -> None:
                progress.close()
                tilia.errors.display(tilia.errors.VELOPACK_UPDATE_FAILED, msg)

            QTimer.singleShot(0, parent, _show_error)

    threading.Thread(target=_apply, daemon=True).start()


def _show_git_dialog(update: tilia.updates.GitUpdateInfo) -> None:
    if update.commits_behind == 0:
        _display_information(
            "Check for Updates", f"Already up to date with {update.upstream}."
        )
        return

    n = update.commits_behind
    if not get(
        Get.FROM_USER_YES_OR_NO,
        "Update Available",
        f"{n} commit{'s' if n != 1 else ''} available on {update.upstream}.\n"
        f"Pull and restart TiLiA now?",
    ):
        return

    result = subprocess.run(
        ["git", "pull", tilia.constants.GITHUB_URL, tilia.updates.GIT_BRANCH],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()
        tilia.errors.display(
            tilia.errors.GIT_PULL_FAILED, output or "git pull returned an error."
        )
        return

    os.execv(sys.executable, [sys.executable, "-m", "tilia"] + sys.argv[1:])
