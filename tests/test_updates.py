"""Regression tests for tilia.updates.

These lock down two things that broke in the wild and are awkward to catch
otherwise (the Velopack code path only runs in compiled builds):

1. `_make_locator` must produce OS-correct paths — `UpdateMac` on macOS,
   `Update.exe` on Windows. A Windows-shaped locator on macOS made
   `UpdateManager(...)` raise, which surfaced as the misleading
   "TiLiA is running from source" dialog.
2. `_run_check` must route every failure mode to a distinct, surfaced message
   instead of swallowing it, and the daemon-thread backstop must never let an
   unexpected error die silently.

The real `velopack` extension is a build-only dependency, so it is faked here
to keep these tests runnable in the normal (source) test environment.
"""

import pathlib
import sys
import types

import pytest

import tilia.errors
import tilia.updates as updates


class _FakeLocatorConfig:
    """Stand-in for velopack.VelopackLocatorConfig that just records kwargs."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeUM:
    """Happy-path UpdateManager: constructs cleanly, reports up to date."""

    def __init__(self, source, locator=None):
        pass

    def check_for_updates(self):
        return None


def _install_fake_velopack(monkeypatch, update_manager=None):
    """Put a fake `velopack` module in sys.modules for the duration of a test.

    Omit ``update_manager`` to make ``from velopack import UpdateManager`` raise
    ImportError (simulating a broken/stripped build).
    """
    mod = types.ModuleType("velopack")
    if update_manager is not None:
        mod.UpdateManager = update_manager
    mod.VelopackLocatorConfig = _FakeLocatorConfig
    monkeypatch.setitem(sys.modules, "velopack", mod)
    return mod


@pytest.fixture
def record(monkeypatch):
    """Capture what _run_check decides: surfaced reports and emitted posts."""
    reports = []
    posts = []
    monkeypatch.setattr(
        updates, "_report", lambda silent, msg: reports.append((silent, msg))
    )
    monkeypatch.setattr(updates, "post", lambda *args, **kwargs: posts.append(args))
    return reports, posts


# --------------------------------------------------------------------------- #
# _make_locator: OS-correct paths
# --------------------------------------------------------------------------- #


def test_make_locator_returns_none_without_manifest(monkeypatch, tmp_path):
    exe = tmp_path / "tilia-bin"
    exe.write_text("")
    monkeypatch.setattr(sys, "executable", str(exe))

    assert updates._make_locator() is None


def test_make_locator_macos_uses_updatemac_and_cache_packages(monkeypatch, tmp_path):
    macos = tmp_path / "TiLiA.app" / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    (macos / "sq.version").write_text("<package/>")
    exe = macos / "TiLiA-bin"
    exe.write_text("")
    home = tmp_path / "home"

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: home))
    _install_fake_velopack(monkeypatch)

    loc = updates._make_locator()

    assert loc is not None
    assert loc.UpdateExePath.endswith("UpdateMac")
    assert "MacOS" in loc.UpdateExePath
    # RootAppDir is the .app bundle, not Contents.
    assert loc.RootAppDir.endswith("TiLiA.app")
    # Packages are staged under the user cache, not the read-only bundle.
    normalized = loc.PackagesDir.replace("\\", "/")
    assert normalized.endswith("Library/Caches/TiLiA/packages")
    assert (home / "Library" / "Caches" / "TiLiA" / "packages").exists()


def test_make_locator_windows_uses_update_exe(monkeypatch, tmp_path):
    current = tmp_path / "current"
    current.mkdir()
    (current / "sq.version").write_text("<package/>")
    exe = current / "TiLiA.exe"
    exe.write_text("")

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", str(exe))
    _install_fake_velopack(monkeypatch)

    loc = updates._make_locator()

    assert loc.UpdateExePath.endswith("Update.exe")
    assert loc.PackagesDir.endswith("packages")
    # On Windows the root is the dir above current/.
    assert loc.RootAppDir == str(tmp_path)


def test_make_locator_macos_mkdir_failure_is_nonfatal(monkeypatch, tmp_path):
    macos = tmp_path / "TiLiA.app" / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    (macos / "sq.version").write_text("<package/>")
    exe = macos / "TiLiA-bin"
    exe.write_text("")

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(
        pathlib.Path, "home", classmethod(lambda cls: tmp_path / "home")
    )

    def boom(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(pathlib.Path, "mkdir", boom)
    _install_fake_velopack(monkeypatch)

    # A read-only home must not abort detection — the locator is still returned.
    loc = updates._make_locator()
    assert loc is not None
    assert loc.UpdateExePath.endswith("UpdateMac")


# --------------------------------------------------------------------------- #
# _run_check: routing of every outcome
# --------------------------------------------------------------------------- #


def test_run_check_dev_environment_uses_git(monkeypatch):
    called = []
    monkeypatch.setattr(updates, "_run_git_check", lambda silent: called.append(silent))
    monkeypatch.delattr(updates, "__compiled__", raising=False)

    updates._run_check(False)

    assert called == [False]


def test_run_check_velopack_import_error_is_reported(monkeypatch, record):
    reports, posts = record
    monkeypatch.setattr(updates, "__compiled__", True, raising=False)
    _install_fake_velopack(monkeypatch, update_manager=None)  # no UpdateManager attr

    updates._run_check(False)

    assert posts == []
    assert len(reports) == 1
    assert "unavailable in this build" in reports[0][1]


def test_run_check_missing_locator_is_reported(monkeypatch, record):
    reports, posts = record
    monkeypatch.setattr(updates, "__compiled__", True, raising=False)
    _install_fake_velopack(monkeypatch, update_manager=FakeUM)
    monkeypatch.setattr(updates, "_make_locator", lambda: None)

    updates._run_check(False)

    assert posts == []
    assert "manifest" in reports[0][1].lower()


def test_run_check_construct_failure_reports_install_error_with_detail(
    monkeypatch, record
):
    reports, posts = record
    monkeypatch.setattr(updates, "__compiled__", True, raising=False)

    class RaisingUM:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("Update.exe does not exist in the expected path")

    _install_fake_velopack(monkeypatch, update_manager=RaisingUM)
    monkeypatch.setattr(updates, "_make_locator", lambda: object())

    updates._run_check(False)

    assert posts == []
    _, msg = reports[0]
    assert "not properly installed" in msg
    assert "Update.exe does not exist" in msg  # underlying cause surfaced


def test_run_check_network_failure_reports_unreachable_with_detail(monkeypatch, record):
    reports, posts = record
    monkeypatch.setattr(updates, "__compiled__", True, raising=False)

    class CheckRaisingUM:
        def __init__(self, *args, **kwargs):
            pass

        def check_for_updates(self):
            raise RuntimeError("Network error: Http error: http status: 404")

    _install_fake_velopack(monkeypatch, update_manager=CheckRaisingUM)
    monkeypatch.setattr(updates, "_make_locator", lambda: object())

    updates._run_check(False)

    assert posts == []
    _, msg = reports[0]
    assert "Couldn't reach the update server" in msg
    assert "404" in msg


def test_run_check_up_to_date_posts_manager(monkeypatch, record):
    reports, posts = record
    monkeypatch.setattr(updates, "__compiled__", True, raising=False)
    _install_fake_velopack(monkeypatch, update_manager=FakeUM)
    monkeypatch.setattr(updates, "_make_locator", lambda: object())

    updates._run_check(False)

    assert reports == []
    assert len(posts) == 1
    # (Post.APP_UPDATE_AVAILABLE, manager, update) — update is None == up to date.
    assert posts[0][2] is None


def test_run_check_up_to_date_silent_stays_quiet(monkeypatch, record):
    reports, posts = record
    monkeypatch.setattr(updates, "__compiled__", True, raising=False)
    _install_fake_velopack(monkeypatch, update_manager=FakeUM)
    monkeypatch.setattr(updates, "_make_locator", lambda: object())

    updates._run_check(True)

    assert reports == []
    assert posts == []


def test_run_check_update_available_is_posted(monkeypatch, record):
    reports, posts = record
    monkeypatch.setattr(updates, "__compiled__", True, raising=False)
    sentinel = object()

    class FakeUMWithUpdate:
        def __init__(self, *args, **kwargs):
            pass

        def check_for_updates(self):
            return sentinel

    _install_fake_velopack(monkeypatch, update_manager=FakeUMWithUpdate)
    monkeypatch.setattr(updates, "_make_locator", lambda: object())

    updates._run_check(True)  # even silent posts when an update exists

    assert reports == []
    assert posts[0][2] is sentinel


def test_run_check_safe_backstops_unexpected_error(monkeypatch, record):
    reports, posts = record
    monkeypatch.setattr(updates, "__compiled__", True, raising=False)
    _install_fake_velopack(monkeypatch, update_manager=FakeUM)

    def boom():
        raise ValueError("something nobody anticipated")

    monkeypatch.setattr(updates, "_make_locator", boom)

    # ValueError is not a RuntimeError — only the outer backstop catches it.
    updates._run_check_safe(False)

    assert posts == []
    assert any("Update check failed" in msg for _, msg in reports)


# --------------------------------------------------------------------------- #
# _report: silent gating + error routing
# --------------------------------------------------------------------------- #


def test_report_silent_check_shows_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(
        tilia.errors, "display", lambda err, *args: calls.append((err, args))
    )

    updates._report(True, "boot-time blip")

    assert calls == []


def test_report_user_check_displays_failure_with_detail(monkeypatch):
    calls = []
    monkeypatch.setattr(
        tilia.errors, "display", lambda err, *args: calls.append((err, args))
    )

    updates._report(False, "the actual reason")

    assert len(calls) == 1
    err, args = calls[0]
    assert err is tilia.errors.VELOPACK_UPDATE_FAILED
    assert args == ("the actual reason",)
