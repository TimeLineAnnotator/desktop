"""Per-computer state, and the atomic write every file the core writes goes through.

`atomic_write` is the core's one implementation of atomic writes: the `.tla`
writer uses it, and so will the per-computer state files.
"""

from __future__ import annotations

import os
import secrets
import stat
import sys
import time
from pathlib import Path

_IS_WINDOWS: bool = sys.platform == "win32"

# Windows refuses to replace a file another program holds open.
_REPLACE_RETRY_INTERVAL = 0.05
_REPLACE_RETRY_TIMEOUT = 1.0


def _replace_with_retry(tmp: Path, path: Path) -> None:
    deadline = time.monotonic() + _REPLACE_RETRY_TIMEOUT
    while True:
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if not _IS_WINDOWS or time.monotonic() >= deadline:
                raise
            time.sleep(_REPLACE_RETRY_INTERVAL)


def _fsync_folder(folder: Path) -> None:
    try:
        fd = os.open(folder, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write(path: Path, data: bytes, *, mode: int | None = None) -> None:
    """Replace ``path`` with ``data`` so that readers never see a partial file.

    The data goes to a temporary file in the same folder, which is flushed to
    disk and then renamed over ``path``. On POSIX the new file gets exactly
    ``mode`` if given, else the permission bits ``path`` already has. If anything
    fails, ``path`` is untouched and the temporary file is removed.
    """
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(tmp, flags, 0o666 if mode is None else mode)
        with os.fdopen(fd, "wb") as f:
            if not _IS_WINDOWS:
                if mode is not None:
                    os.chmod(tmp, mode)
                elif path.exists():
                    os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        _replace_with_retry(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
    if not _IS_WINDOWS:
        _fsync_folder(path.parent)
