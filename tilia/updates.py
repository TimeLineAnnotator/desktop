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
    to sys.executable (i.e. we are running from a Velopack-managed current/ dir).
    Returns None in dev / non-Velopack environments.
    """
    import sys
    from pathlib import Path

    current_dir = Path(sys.executable).parent
    if not (current_dir / "sq.version").exists():
        return None

    from velopack import VelopackLocatorConfig

    root_dir = current_dir.parent
    return VelopackLocatorConfig(
        RootAppDir=str(root_dir),
        UpdateExePath=str(root_dir / "Update.exe"),
        PackagesDir=str(root_dir / "packages"),
        ManifestPath=str(current_dir / "sq.version"),
        CurrentBinaryDir=str(current_dir),
        IsPortable=False,
    )


def _run_check(silent: bool) -> None:
    if "__compiled__" not in globals():
        _run_git_check(silent)
        return

    try:
        from velopack import UpdateManager
    except ImportError:
        _post_unavailable(silent)
        return

    locator = _make_locator()
    if locator is None:
        import tilia.errors

        tilia.errors.display(tilia.errors.VELOPACK_MANIFEST_NOT_FOUND)
        _post_unavailable(silent)
        return

    try:
        manager: UpdateManager = UpdateManager(GITHUB_URL, locator=locator)
    except RuntimeError:
        _post_unavailable(silent)
        return

    try:
        update: UpdateInfo | None = manager.check_for_updates()
    except Exception:
        if not silent:
            post(Post.APP_UPDATE_AVAILABLE, manager, None)
        return

    if update is not None or not silent:
        post(Post.APP_UPDATE_AVAILABLE, manager, update)


def check_for_updates(silent: bool = False) -> None:
    """Check for updates in a background thread.

    When silent=True (startup check), only posts if an update is found.
    When silent=False (user-triggered), always posts so the UI can report status.
    """
    threading.Thread(target=_run_check, args=(silent,), daemon=True).start()
