from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from tilia.constants import GITHUB_URL
from tilia.requests import Post, post

if TYPE_CHECKING:
    from velopack import UpdateInfo, UpdateManager


GIT_BRANCH = "main"


@dataclass
class GitUpdateInfo:
    commits_behind: int
    branch: str
    upstream: str


def _post_unavailable(silent: bool) -> None:
    if not silent:
        post(Post.APP_UPDATE_AVAILABLE, None, None)


def _run_git_check(silent: bool) -> None:
    """Check for new commits via git (used when not running as a Velopack install)."""
    try:
        fetch = subprocess.run(
            ["git", "fetch", GITHUB_URL, GIT_BRANCH],
            capture_output=True,
            timeout=15,
            check=False,
        )
        if fetch.returncode != 0:
            _post_unavailable(silent)
            return

        # After fetching by URL the ref lands in FETCH_HEAD.
        rev_result = subprocess.run(
            ["git", "rev-list", "HEAD..FETCH_HEAD", "--count"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if rev_result.returncode != 0:
            _post_unavailable(silent)
            return

        count = int(rev_result.stdout.strip())

        branch_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        branch = (
            branch_result.stdout.strip() if branch_result.returncode == 0 else "HEAD"
        )

        if count > 0 or not silent:
            post(
                Post.APP_UPDATE_AVAILABLE,
                None,
                GitUpdateInfo(count, branch, f"{GITHUB_URL}/tree/{GIT_BRANCH}"),
            )

    except (subprocess.TimeoutExpired, subprocess.SubprocessError, ValueError):
        _post_unavailable(silent)


def _make_locator():
    """Build an explicit VelopackLocatorConfig when sq.version is present next
    to sys.executable (i.e. we are running from a Velopack-managed install).
    Returns None in dev / non-Velopack environments.

    The Velopack layout differs by OS, so the paths must be branched:

    - Windows: ``<root>/Update.exe`` with ``current/`` and ``packages/`` dirs
      next to it; the executable lives in ``<root>/current/``.
    - macOS: ``<App>.app/Contents/MacOS/{UpdateMac, sq.version}``; the bundle is
      installed read-only (and root-owned via the .pkg), so updates are staged
      under the user Library cache rather than inside the bundle.
    - Linux: an AppImage, FUSE-mounted at runtime under ``<mount>/usr/bin/``.
      RootAppDir has to be the AppImage's own file path, from the $APPIMAGE
      env var the AppImage runtime sets - the mount point is a fresh temp dir
      every launch, useless as a stable identity. There is no per-user "app
      data" dir to stage updates in the way macOS's Library/Caches is, so
      PackagesDir follows Velopack's own convention: a fixed, packId-scoped
      spot under /var/tmp. IsPortable=True, unlike the other two: nothing
      "installs" an AppImage.
    """
    import os
    import sys
    from pathlib import Path

    from tilia.constants import APP_NAME

    current_dir = Path(sys.executable).parent
    if not (current_dir / "sq.version").exists():
        return None

    from velopack import VelopackLocatorConfig

    is_portable = False
    if sys.platform == "darwin":
        root_dir = current_dir.parents[1]  # <App>.app
        update_exe = current_dir / "UpdateMac"
        packages_dir = Path.home() / "Library" / "Caches" / APP_NAME / "packages"
        # Best-effort: PackagesDir only stages downloads, it is not needed to
        # detect updates. A read-only home must not abort the whole check.
        try:
            packages_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    elif sys.platform.startswith("linux"):
        appimage_path = os.environ.get("APPIMAGE")
        if not appimage_path:
            # Not actually running as a mounted AppImage (e.g. a raw
            # extracted binary) - nothing Velopack-manageable to locate.
            return None
        root_dir = Path(appimage_path)
        mount_dir = current_dir.parents[1]  # current_dir is <mount>/usr/bin
        update_exe = mount_dir / "UpdateNix"
        packages_dir = Path("/var/tmp/velopack") / APP_NAME / "packages"
        is_portable = True
    elif sys.platform == "win32":
        root_dir = current_dir.parent
        update_exe = root_dir / "Update.exe"
        packages_dir = root_dir / "packages"
    else:
        return None

    return VelopackLocatorConfig(
        RootAppDir=str(root_dir),
        UpdateExePath=str(update_exe),
        PackagesDir=str(packages_dir),
        ManifestPath=str(current_dir / "sq.version"),
        CurrentBinaryDir=str(current_dir),
        IsPortable=is_portable,
    )


def _report(silent: bool, message: str) -> None:
    """Surface an update-check failure to the user.

    Silent (startup) checks stay quiet — we don't want an error popup on every
    boot when, e.g., the network is merely unavailable.
    """
    if silent:
        return
    # _report always runs on check_for_updates' background thread. Post.DISPLAY_ERROR
    # is dispatched synchronously (tilia/requests/post.py), so an un-marshaled call
    # here would build/exec() a QMessageBox off the main thread and crash — same
    # failure mode QtUI.on_update_available's success path already avoids via
    # QTimer.singleShot with a context object (schedules on that object's thread).
    # check_for_updates is only ever invoked from QtUI, so a QApplication with a
    # running event loop is guaranteed to exist here.
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    import tilia.errors

    QTimer.singleShot(
        0,
        QApplication.instance(),
        lambda: tilia.errors.display(tilia.errors.VELOPACK_UPDATE_FAILED, message),
    )


def _run_check(silent: bool) -> None:
    if "__compiled__" not in globals():
        _run_git_check(silent)
        return

    try:
        from velopack import UpdateManager
    except ImportError:
        _report(silent, "Update components are unavailable in this build.")
        return

    locator = _make_locator()
    if locator is None:
        _report(silent, "Could not locate the Velopack app manifest (sq.version).")
        return

    try:
        manager: UpdateManager = UpdateManager(GITHUB_URL, locator=locator)
    except RuntimeError as e:
        _report(silent, f"TiLiA is not properly installed.\n\n{e}")
        return

    try:
        update: UpdateInfo | None = manager.check_for_updates()
    except RuntimeError as e:
        _report(silent, f"Couldn't reach the update server.\n\n{e}")
        return

    if update is not None or not silent:
        post(Post.APP_UPDATE_AVAILABLE, manager, update)


def _run_check_safe(silent: bool) -> None:
    """Backstop so an unexpected error never kills the daemon thread silently.

    The staged handlers in _run_check tighten on RuntimeError (everything
    Velopack raises); this catches anything else — including our own bugs — and
    still reports it instead of letting the thread die without a trace.
    """
    try:
        _run_check(silent)
    except Exception as e:  # noqa: BLE001 - last-resort guard for a daemon thread
        _report(silent, f"Update check failed.\n\n{e}")


def check_for_updates(silent: bool = False) -> None:
    """Check for updates in a background thread.

    When silent=True (startup check), only posts if an update is found and stays
    quiet on failure. When silent=False (user-triggered), always reports status:
    an update is available, TiLiA is up to date, or why the check failed.
    """
    threading.Thread(target=_run_check_safe, args=(silent,), daemon=True).start()
