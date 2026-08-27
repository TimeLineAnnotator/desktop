"""Tests for tilia.lifecycle.

lifecycle.py runs before the UI exists — Velopack invokes it with hook flags on
install/update/uninstall, and boot.py calls init() inside a `__compiled__`
guard. None of that is reachable through commands.execute, so these tests call
the functions directly; that is the right level for boot-time code.

Every platform-specific import in lifecycle.py is function-local
(`import winreg`, `import ctypes`, `import shutil`), which is what makes the
Windows path testable from any OS: swapping sys.modules["winreg"] for a fake is
enough. The Linux path needs no faking at all beyond XDG_DATA_HOME.
"""

import ctypes
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

import tilia.lifecycle as lifecycle

# --------------------------------------------------------------------------- #
# Windows: in-memory registry double
# --------------------------------------------------------------------------- #


class _FakeKey:
    """Handle returned by CreateKeyEx/OpenKey; usable as a context manager."""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeRegistry:
    """Stand-in for the winreg surface lifecycle.py uses.

    Keys are stored flat, keyed by their backslash-separated path, so "does
    this key have subkeys" is a prefix test. DeleteKey mirrors the real API and
    refuses to delete a key that still has subkeys — that constraint is the
    whole point of test_uninstall_removes_the_tla_key.
    """

    HKEY_CURRENT_USER = "HKCU"
    REG_SZ = 1

    def __init__(self):
        self.keys = {}

    def _has_subkeys(self, path):
        return any(p.startswith(path + "\\") for p in self.keys)

    def CreateKeyEx(self, root, path):
        parts = path.split("\\")
        for i in range(1, len(parts) + 1):
            self.keys.setdefault("\\".join(parts[:i]), {})
        return _FakeKey(path)

    def OpenKey(self, root, path):
        if path not in self.keys:
            raise FileNotFoundError(2, "cannot find the file specified", path)
        return _FakeKey(path)

    def SetValueEx(self, key, name, reserved, type_, value):
        self.keys[key.path][name] = value

    def QueryValueEx(self, key, name):
        if name not in self.keys[key.path]:
            raise FileNotFoundError(2, "cannot find the file specified", name)
        return self.keys[key.path][name], self.REG_SZ

    def DeleteValue(self, key, name):
        if name not in self.keys[key.path]:
            raise FileNotFoundError(2, "cannot find the file specified", name)
        del self.keys[key.path][name]

    def DeleteKey(self, root, path):
        if path not in self.keys:
            raise FileNotFoundError(2, "cannot find the file specified", path)
        if self._has_subkeys(path):
            raise OSError(41, "the directory is not empty", path)
        del self.keys[path]


class _FakeShell32:
    def __init__(self):
        self.calls = []

        def SHChangeNotify(*args):
            self.calls.append(args)

        self.SHChangeNotify = SHChangeNotify


@pytest.fixture
def registry(monkeypatch):
    """Fake winreg + ctypes.windll so the Windows path runs on any OS."""
    reg = FakeRegistry()
    shell32 = _FakeShell32()
    monkeypatch.setitem(sys.modules, "winreg", reg)
    # ctypes.windll does not exist off Windows, hence raising=False.
    monkeypatch.setattr(
        ctypes, "windll", types.SimpleNamespace(shell32=shell32), raising=False
    )
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\test\AppData\Local")
    reg.shell32 = shell32
    return reg


class TestWindowsFileAssociation:
    def test_register_writes_progid_and_open_with_entries(self, registry):
        lifecycle._register_windows_file_association()

        assert registry.keys[r"Software\Classes\.tla"][""] == "TiLiA.tla"
        assert registry.keys[r"Software\Classes\TiLiA.tla"][""] == "TiLiA File"
        # advertises TiLiA as a candidate in the "Open with" submenu
        assert "TiLiA.tla" in registry.keys[r"Software\Classes\.tla\OpenWithProgids"]
        app_key = r"Software\Classes\Applications\TiLiA.exe"
        assert registry.keys[app_key]["FriendlyAppName"] == "TiLiA"
        assert ".tla" in registry.keys[rf"{app_key}\SupportedTypes"]

    def test_register_points_commands_at_the_velopack_current_path(self, registry):
        lifecycle._register_windows_file_association()

        # Built with Path, so the separator follows the host OS; on Windows,
        # where this code actually runs, that is a backslash.
        expected = (
            Path(r"C:\Users\test\AppData\Local") / "TiLiA" / "current" / ("TiLiA.exe")
        )
        for key in (
            r"Software\Classes\TiLiA.tla\shell\open\command",
            r"Software\Classes\Applications\TiLiA.exe\shell\open\command",
        ):
            assert registry.keys[key][""] == f'"{expected}" "%1"'
        assert registry.keys[r"Software\Classes\TiLiA.tla\DefaultIcon"][""] == (
            f"{expected},0"
        )

    def test_register_notifies_the_shell(self, registry):
        lifecycle._register_windows_file_association()

        # SHCNE_ASSOCCHANGED, or Explorer keeps showing the old icon/handler.
        assert registry.shell32.calls == [(0x08000000, 0x0000, None, None)]

    def test_uninstall_removes_the_progid_and_app_keys(self, registry):
        lifecycle._register_windows_file_association()
        lifecycle._unregister_windows_file_association()

        assert r"Software\Classes\TiLiA.tla" not in registry.keys
        assert r"Software\Classes\Applications\TiLiA.exe" not in registry.keys

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "_unregister deletes .tla before removing its OpenWithProgids subkey, "
            "and DeleteKey refuses a key with subkeys. See review comment on "
            "tilia/lifecycle.py:102."
        ),
    )
    def test_uninstall_removes_the_tla_key(self, registry):
        lifecycle._register_windows_file_association()
        lifecycle._unregister_windows_file_association()

        assert r"Software\Classes\.tla" not in registry.keys

    def test_uninstall_leaves_a_foreign_handler_alone(self, registry):
        """Another app owns .tla — we must not delete its association."""
        with registry.CreateKeyEx(registry.HKEY_CURRENT_USER, r"Software\Classes\.tla"):
            pass
        registry.keys[r"Software\Classes\.tla"][""] = "OtherApp.tla"

        lifecycle._unregister_windows_file_association()

        assert registry.keys[r"Software\Classes\.tla"][""] == "OtherApp.tla"

    def test_uninstall_is_safe_when_nothing_was_registered(self, registry):
        lifecycle._unregister_windows_file_association()  # must not raise

        assert registry.keys == {}


# --------------------------------------------------------------------------- #
# Linux: XDG desktop entry + MIME package
# --------------------------------------------------------------------------- #


@pytest.fixture
def xdg(tmp_path, monkeypatch):
    """Point XDG_DATA_HOME at a temp dir and stub out the refresh tools."""
    data_home = tmp_path / "share"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setattr(sys, "executable", "/opt/tilia/current/TiLiA")
    monkeypatch.setattr(shutil, "which", lambda _: None)
    return data_home


def _desktop_file(data_home):
    return data_home / "applications" / "tilia.desktop"


def _mime_file(data_home):
    return data_home / "mime" / "packages" / "tilia.xml"


class TestLinuxFileAssociation:
    def test_register_writes_desktop_entry(self, xdg):
        lifecycle._register_linux_file_association()

        content = _desktop_file(xdg).read_text()
        assert "Exec=/opt/tilia/current/TiLiA %F" in content
        assert "MimeType=application/x-tilia;" in content

    def test_register_writes_mime_package(self, xdg):
        lifecycle._register_linux_file_association()

        content = _mime_file(xdg).read_text()
        assert 'mime-type type="application/x-tilia"' in content
        assert 'glob pattern="*.tla"' in content

    def test_register_refreshes_databases_when_tools_are_present(
        self, xdg, monkeypatch
    ):
        monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
        calls = []
        monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd))

        lifecycle._register_linux_file_association()

        assert [cmd[0] for cmd in calls] == [
            "update-mime-database",
            "update-desktop-database",
        ]

    def test_unregister_removes_both_files(self, xdg):
        lifecycle._register_linux_file_association()

        lifecycle._unregister_linux_file_association()

        assert not _desktop_file(xdg).exists()
        assert not _mime_file(xdg).exists()

    def test_unregister_is_safe_when_nothing_was_registered(self, xdg):
        lifecycle._unregister_linux_file_association()  # must not raise

        assert not _desktop_file(xdg).exists()

    def test_ensure_does_not_rewrite_a_current_entry(self, xdg, monkeypatch):
        lifecycle._register_linux_file_association()
        calls = []
        monkeypatch.setattr(
            lifecycle, "_register_linux_file_association", lambda: calls.append(1)
        )

        lifecycle._ensure_linux_file_association()

        assert calls == []

    def test_ensure_rewrites_after_the_executable_moved(self, xdg, monkeypatch):
        """The update case: Velopack swaps in a new current/ directory."""
        lifecycle._register_linux_file_association()
        monkeypatch.setattr(sys, "executable", "/opt/tilia/current-2/TiLiA")

        lifecycle._ensure_linux_file_association()

        assert "Exec=/opt/tilia/current-2/TiLiA %F" in _desktop_file(xdg).read_text()

    def test_ensure_writes_a_missing_entry(self, xdg):
        lifecycle._ensure_linux_file_association()

        assert _desktop_file(xdg).exists()


# --------------------------------------------------------------------------- #
# Velopack hook dispatch
# --------------------------------------------------------------------------- #


@pytest.fixture
def hooks(monkeypatch):
    """Record which lifecycle hook fired, with the version it was handed."""
    calls = []
    monkeypatch.setattr(
        lifecycle, "_on_velopack_install", lambda v: calls.append(("install", v))
    )
    monkeypatch.setattr(
        lifecycle, "_on_velopack_uninstall", lambda v: calls.append(("uninstall", v))
    )
    return calls


class TestHookDispatch:
    @pytest.mark.parametrize(
        "flag,expected",
        [
            ("--veloapp-install", [("install", "1.2.3")]),
            ("--veloapp-updated", [("install", "1.2.3")]),
            ("--veloapp-uninstall", [("uninstall", "1.2.3")]),
            ("--veloapp-obsolete", []),
            ("--veloapp-firstrun", []),
        ],
    )
    def test_flag_dispatches_to_the_right_hook(
        self, hooks, monkeypatch, flag, expected
    ):
        monkeypatch.setattr(sys, "argv", ["TiLiA", flag, "1.2.3"])

        assert lifecycle._run_hook_from_argv() is True
        assert hooks == expected

    def test_missing_version_argument_is_tolerated(self, hooks, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["TiLiA", "--veloapp-install"])

        assert lifecycle._run_hook_from_argv() is True
        assert hooks == [("install", "")]

    def test_normal_launch_is_not_a_hook(self, hooks, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["TiLiA", "some_file.tla"])

        assert lifecycle._run_hook_from_argv() is False
        assert hooks == []

    def test_velopack_prefix_is_not_a_hook_flag(self, hooks, monkeypatch):
        # Regression: the hooks first shipped matching --velopack-*, but
        # Velopack passes --veloapp-*, so they never fired and no file
        # association was ever written.
        monkeypatch.setattr(sys, "argv", ["TiLiA", "--velopack-install", "1.2.3"])

        assert lifecycle._run_hook_from_argv() is False
        assert hooks == []


class TestPlatformDispatch:
    @pytest.mark.parametrize(
        "platform,expected",
        [("win32", ["windows"]), ("linux", ["linux"]), ("darwin", [])],
    )
    def test_install_registers_for_the_running_platform(
        self, monkeypatch, platform, expected
    ):
        calls = []
        monkeypatch.setattr(sys, "platform", platform)
        monkeypatch.setattr(
            lifecycle,
            "_register_windows_file_association",
            lambda: calls.append("windows"),
        )
        monkeypatch.setattr(
            lifecycle, "_register_linux_file_association", lambda: calls.append("linux")
        )

        lifecycle._on_velopack_install("1.2.3")

        assert calls == expected

    @pytest.mark.parametrize(
        "platform,expected",
        [("win32", ["windows"]), ("linux", ["linux"]), ("darwin", [])],
    )
    def test_uninstall_unregisters_for_the_running_platform(
        self, monkeypatch, platform, expected
    ):
        calls = []
        monkeypatch.setattr(sys, "platform", platform)
        monkeypatch.setattr(
            lifecycle,
            "_unregister_windows_file_association",
            lambda: calls.append("windows"),
        )
        monkeypatch.setattr(
            lifecycle,
            "_unregister_linux_file_association",
            lambda: calls.append("linux"),
        )

        lifecycle._on_velopack_uninstall("1.2.3")

        assert calls == expected


# --------------------------------------------------------------------------- #
# init()
# --------------------------------------------------------------------------- #


@pytest.fixture
def velopack_app(monkeypatch):
    """Record whether the Velopack SDK's own App().run() was invoked."""
    calls = []
    monkeypatch.setattr(lifecycle, "_run_velopack_app", lambda: calls.append(1))
    return calls


class TestInit:
    def test_hook_mode_runs_the_hook_and_exits(self, hooks, velopack_app, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["TiLiA", "--veloapp-install", "1.2.3"])

        with pytest.raises(SystemExit) as exc:
            lifecycle.init()

        assert exc.value.code == 0
        assert hooks == [("install", "1.2.3")]
        assert velopack_app == [1]

    def test_normal_launch_does_not_exit(self, hooks, velopack_app, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["TiLiA"])
        monkeypatch.setattr(sys, "platform", "win32")

        lifecycle.init()

        assert hooks == []
        assert velopack_app == [1]

    def test_linux_association_is_ensured_only_on_linux(
        self, velopack_app, monkeypatch
    ):
        calls = []
        monkeypatch.setattr(sys, "argv", ["TiLiA"])
        monkeypatch.setattr(
            lifecycle, "_ensure_linux_file_association", lambda: calls.append(1)
        )

        monkeypatch.setattr(sys, "platform", "darwin")
        lifecycle.init()
        assert calls == []

        monkeypatch.setattr(sys, "platform", "linux")
        lifecycle.init()
        assert calls == [1]
