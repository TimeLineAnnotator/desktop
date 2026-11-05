"""
Platform integration for compiled builds: Velopack lifecycle hooks and
OS-level file association registration.

Entry point: call `init()` once at startup, inside a `"__compiled__" in globals()` guard.
"""

import os
import sys
from pathlib import Path

from tilia.constants import FILE_EXTENSION

_TLA_PROGID = "TiLiA.tla"
_TLA_EXT_KEY = r"Software\Classes\.tla"
_TLA_PROGID_KEY = rf"Software\Classes\{_TLA_PROGID}"
_APP_KEY = r"Software\Classes\Applications\TiLiA.exe"
_TILIA_MIME_TYPE = "application/x-tilia"


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------


def _register_windows_file_association() -> None:
    import ctypes
    import winreg

    from tilia.constants import APP_NAME

    # %LOCALAPPDATA%\<AppName>\current\ is the stable Velopack-managed path.
    localappdata = os.environ.get("LOCALAPPDATA", "")
    current_exe = Path(localappdata) / APP_NAME / "current" / f"{APP_NAME}.exe"

    # --- ProgID block (.tla → TiLiA.tla) ---
    # Maps the .tla extension to our ProgID so Windows knows which handler owns it.
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _TLA_EXT_KEY) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, _TLA_PROGID)
    # Human-readable label shown in Explorer's "Type" column.
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _TLA_PROGID_KEY) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "TiLiA File")
    # Icon displayed on .tla files in Explorer.
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, rf"{_TLA_PROGID_KEY}\DefaultIcon"
    ) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f"{current_exe},0")
    # Command executed on double-click.
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, rf"{_TLA_PROGID_KEY}\shell\open\command"
    ) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{current_exe}" "%1"')

    # --- "Open with" submenu ---
    # Without this entry TiLiA is absent from the right-click "Open with" list
    # even though it is the default handler (the ProgID block above only sets
    # the default; this explicitly advertises TiLiA as a candidate).
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, rf"{_TLA_EXT_KEY}\OpenWithProgids"
    ) as k:
        winreg.SetValueEx(k, _TLA_PROGID, 0, winreg.REG_SZ, "")

    # --- Applications\TiLiA.exe block ---
    # Registers TiLiA in the per-app namespace so it appears in
    # "Choose another app" and the "Open with" dialog with icon + name.
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _APP_KEY) as k:
        winreg.SetValueEx(k, "FriendlyAppName", 0, winreg.REG_SZ, "TiLiA")
    # Icon shown next to TiLiA in the "Open with" / "Choose another app" dialogs.
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, rf"{_APP_KEY}\DefaultIcon") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f"{current_exe},0")
    # Command used when the user picks TiLiA via "Choose another app".
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, rf"{_APP_KEY}\shell\open\command"
    ) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{current_exe}" "%1"')
    # Tells Windows which extensions this app handles, used to filter
    # the "Open with" list so TiLiA only appears for .tla files.
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, rf"{_APP_KEY}\SupportedTypes"
    ) as k:
        winreg.SetValueEx(k, f".{FILE_EXTENSION}", 0, winreg.REG_SZ, "")

    # Tell the shell to refresh file association icons/handlers
    shell32 = ctypes.windll.shell32
    shell32.SHChangeNotify.restype = None
    shell32.SHChangeNotify.argtypes = [
        ctypes.c_long,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    shell32.SHChangeNotify(0x08000000, 0x0000, None, None)


def _unregister_windows_file_association() -> None:
    import winreg

    open_with_key = rf"{_TLA_EXT_KEY}\OpenWithProgids"

    # OpenWithProgids is a subkey of .tla, and DeleteKey refuses to remove a
    # key that still has subkeys - so our value has to come out of it (and the
    # now-possibly-empty subkey removed) before .tla itself can be deleted.
    # Only our own value is touched: other apps can have entries of their own
    # in OpenWithProgids, and those must survive our uninstall.
    key_now_empty = False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, open_with_key, 0, winreg.KEY_ALL_ACCESS
        ) as k:
            try:
                winreg.DeleteValue(k, _TLA_PROGID)
            except OSError:
                pass
            num_subkeys, num_values, _ = winreg.QueryInfoKey(k)
            key_now_empty = num_subkeys == 0 and num_values == 0
    except OSError:
        pass

    if key_now_empty:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, open_with_key)
        except OSError:
            pass

    # Only remove .tla itself if we own it.
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _TLA_EXT_KEY) as k:
            if winreg.QueryValueEx(k, "")[0] == _TLA_PROGID:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _TLA_EXT_KEY)
    except OSError:
        pass

    for subkey in [
        rf"{_TLA_PROGID_KEY}\shell\open\command",
        rf"{_TLA_PROGID_KEY}\shell\open",
        rf"{_TLA_PROGID_KEY}\shell",
        rf"{_TLA_PROGID_KEY}\DefaultIcon",
        _TLA_PROGID_KEY,
        rf"{_APP_KEY}\shell\open\command",
        rf"{_APP_KEY}\shell\open",
        rf"{_APP_KEY}\shell",
        rf"{_APP_KEY}\DefaultIcon",
        rf"{_APP_KEY}\SupportedTypes",
        _APP_KEY,
    ]:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, subkey)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Linux
# ---------------------------------------------------------------------------


def _stable_appimage_path() -> Path:
    """Where the running AppImage gets copied to on first integration.

    Matches how AppImageLauncher-style self-integration normally works: a
    stable copy separate from wherever the user happened to download the
    file to, so moving/deleting the original doesn't silently break the
    desktop launcher entry.
    """
    from tilia.constants import APP_NAME

    bin_dir = Path(os.environ.get("XDG_BIN_HOME", str(Path.home() / ".local" / "bin")))
    return bin_dir / f"{APP_NAME}.AppImage"


def _ensure_stable_appimage_copy() -> str | None:
    """Copy the running AppImage to its stable location if not already
    running from there. Returns the stable path, or None if not running as a
    mounted AppImage at all (e.g. a raw extracted binary) - matches the
    APPIMAGE check _make_locator (tilia/updates.py) makes for the same reason.
    """
    import shutil

    appimage_path = os.environ.get("APPIMAGE")
    if not appimage_path:
        return None

    source = Path(appimage_path).resolve()
    stable = _stable_appimage_path()
    if stable.exists() and source == stable.resolve():
        return str(stable)

    stable.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, stable)
    return str(stable)


def _register_linux_file_association(exec_path: str | None = None) -> None:
    import shutil
    import subprocess

    exe = exec_path or sys.executable
    xdg_data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))

    mime_dir = xdg_data / "mime" / "packages"
    mime_dir.mkdir(parents=True, exist_ok=True)
    (mime_dir / "tilia.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">\n'
        f'  <mime-type type="{_TILIA_MIME_TYPE}">\n'
        f"    <comment>TiLiA File</comment>\n"
        f'    <glob pattern="*.{FILE_EXTENSION}"/>\n'
        f"  </mime-type>\n"
        f"</mime-info>\n",
        encoding="utf-8",
    )
    if shutil.which("update-mime-database"):
        subprocess.run(["update-mime-database", str(xdg_data / "mime")], check=False)

    apps_dir = xdg_data / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    (apps_dir / "tilia.desktop").write_text(
        f"[Desktop Entry]\n"
        f"Type=Application\n"
        f"Name=TiLiA\n"
        f"Exec={exe} %F\n"
        f"MimeType={_TILIA_MIME_TYPE};\n"
        f"NoDisplay=true\n",
        encoding="utf-8",
    )
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(apps_dir)], check=False)


def _unregister_linux_file_association() -> None:
    import shutil
    import subprocess

    xdg_data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))

    mime_file = xdg_data / "mime" / "packages" / "tilia.xml"
    if mime_file.exists():
        mime_file.unlink()
        if shutil.which("update-mime-database"):
            subprocess.run(
                ["update-mime-database", str(xdg_data / "mime")], check=False
            )

    desktop_file = xdg_data / "applications" / "tilia.desktop"
    if desktop_file.exists():
        desktop_file.unlink()
        if shutil.which("update-desktop-database"):
            subprocess.run(
                ["update-desktop-database", str(xdg_data / "applications")],
                check=False,
            )


def _remove_stable_appimage_copy() -> None:
    _stable_appimage_path().unlink(missing_ok=True)


def _ensure_linux_file_association() -> None:
    try:
        exe = _ensure_stable_appimage_copy() or sys.executable
        xdg_data = Path(
            os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))
        )
        desktop_file = xdg_data / "applications" / "tilia.desktop"
        if desktop_file.exists() and f"Exec={exe} " in desktop_file.read_text():
            return
        _register_linux_file_association(exe)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# In-app "Uninstall" command
# ---------------------------------------------------------------------------
#
# Registration-only: removes file associations / Launch Services entry, never
# touches user data (QSettings, autosaves, logs, recent files).
#
# Windows isn't handled here: Velopack already registers a proper
# Add/Remove Programs entry there, which is the normal, complete way to
# uninstall a Windows app - a second, partial uninstall path inside the app
# itself would just be a confusing duplicate.


def _macos_app_bundle_path() -> Path | None:
    # sys.executable is <App>.app/Contents/MacOS/<exe>.
    bundle = Path(sys.executable).parents[2]
    return bundle if bundle.suffix == ".app" else None


def _uninstall_macos() -> str:
    import subprocess

    bundle = _macos_app_bundle_path()
    if bundle is not None:
        lsregister = (
            "/System/Library/Frameworks/CoreServices.framework/Frameworks/"
            "LaunchServices.framework/Support/lsregister"
        )
        try:
            subprocess.run([lsregister, "-u", str(bundle)], check=False)
        except OSError:
            pass
    return (
        "TiLiA's file association has been removed. Drag TiLiA to the Trash "
        "to finish uninstalling."
    )


def _uninstall_linux() -> str:
    _unregister_linux_file_association()
    _remove_stable_appimage_copy()
    return (
        "TiLiA's file associations and app-menu entry have been removed. "
        "You can now delete the TiLiA.AppImage file to finish uninstalling."
    )


def uninstall() -> str:
    """Remove OS-level registration for the current platform.

    Returns a message describing what happened / what the user should still
    do, for the caller to display. Safe to call repeatedly, and when nothing
    was registered in the first place.
    """
    if sys.platform == "darwin":
        return _uninstall_macos()
    if sys.platform == "linux":
        return _uninstall_linux()
    if sys.platform == "win32":
        return (
            "On Windows, use Add/Remove Programs (in Settings > Apps) to "
            "uninstall TiLiA - it's already registered there."
        )
    return "Uninstall isn't available on this platform."


# ---------------------------------------------------------------------------
# Velopack lifecycle hooks
# ---------------------------------------------------------------------------


def _on_velopack_install(version: str) -> None:
    try:
        if sys.platform == "win32":
            _register_windows_file_association()
        elif sys.platform == "linux":
            _register_linux_file_association()
    except Exception:
        pass


def _on_velopack_uninstall(version: str) -> None:
    # Same cleanup as the in-app uninstall() command, so this does the right
    # thing if Velopack (or some future packaging change) ever does fire this
    # hook on Linux/macOS - and CI can exercise it directly (no CLI, no GUI
    # automation available here) via the same argv flag Windows already uses.
    try:
        if sys.platform == "win32":
            _unregister_windows_file_association()
        elif sys.platform == "linux":
            _unregister_linux_file_association()
            _remove_stable_appimage_copy()
        elif sys.platform == "darwin":
            _uninstall_macos()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _run_hook_from_argv() -> bool:
    """Parse --velopack-* args and call the appropriate hook directly.

    Returns True if a hook arg was found (caller should sys.exit(0)).
    The Velopack Python SDK only accepts C-level built-in callables via
    its callback registration API, so we parse argv manually instead.
    """
    args = sys.argv[1:]
    for flag, handler in [
        ("--veloapp-install", _on_velopack_install),
        ("--veloapp-updated", _on_velopack_install),
        ("--veloapp-obsolete", lambda v: None),
        ("--veloapp-uninstall", _on_velopack_uninstall),
        ("--veloapp-firstrun", lambda v: None),
    ]:
        if flag in args:
            idx = args.index(flag)
            version = args[idx + 1] if idx + 1 < len(args) else ""
            handler(version)
            return True
    return False


def _run_velopack_app() -> None:
    try:
        from velopack import App as VelopackApp

        VelopackApp().run()
    except SystemExit:
        raise
    except Exception:
        pass


def init() -> None:
    """Run Velopack lifecycle hooks and any first-run OS integration.

    Must be called before QApplication is created, inside a
    ``"__compiled__" in globals()`` guard.
    """
    _hook_mode = any(a.startswith("--veloapp") for a in sys.argv[1:])

    # Parse hook args manually — the Velopack Python SDK only accepts
    # C-level built-in callables via on_*_callback(), so we bypass it.
    if _hook_mode:
        _run_hook_from_argv()
        # Also let the SDK run() handle its own lifecycle (update checks etc.)
        _run_velopack_app()
        sys.exit(0)

    # Normal (non-hook) startup: let the SDK auto-apply any pending update.
    _run_velopack_app()

    if sys.platform == "linux":
        _ensure_linux_file_association()
