"""Per-computer state kept in versioned TOML files in a per-user folder.

Files are read and written with tomlkit, so comments, key order and keys this
code doesn't know all survive a rewrite: users may edit the files by hand, and
an older TiLiA must not lose what a newer one wrote. Every file has a top-level
integer ``version``, and every write is atomic.
"""

from __future__ import annotations

import logging
import os
import secrets
import stat
import sys
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from pathlib import Path

import platformdirs
import tomlkit

logger = logging.getLogger(__name__)

APP_NAME = "TiLiA"
APP_AUTHOR = "TiLiA"
FOLDER = "library"

_IS_WINDOWS: bool = sys.platform == "win32"

# Windows refuses to replace a file another program holds open.
_REPLACE_RETRY_INTERVAL = 0.05
_REPLACE_RETRY_TIMEOUT = 1.0

Migration = Callable[[tomlkit.TOMLDocument], None]


def state_dir() -> Path:
    """Return the folder holding the state files, without creating it."""
    return (
        Path(platformdirs.user_data_dir(APP_NAME, APP_AUTHOR, roaming=False)) / FOLDER
    )


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


def _valid_version(doc: tomlkit.TOMLDocument) -> str | None:
    """Return why the document's version is unusable, or None if it's fine."""
    if "version" not in doc:
        return "it has no version"
    version = doc["version"]
    if isinstance(version, bool) or not isinstance(version, int):
        return "its version is not an integer"
    if version < 1:
        return "its version is less than 1"
    return None


class StateFile:
    """A versioned TOML file that is migrated, never lost and never downgraded."""

    def __init__(
        self,
        path: Path,
        current_version: int,
        migrations: Mapping[int, Migration] | None = None,
    ) -> None:
        if current_version < 1:
            raise ValueError("current_version must be at least 1")
        self._migrations: dict[int, Migration] = dict(migrations or {})
        for version in range(1, current_version):
            if version not in self._migrations:
                raise ValueError(f"no migration from version {version}")
        self.path: Path = Path(path)
        self.current_version: int = current_version
        self.set_aside_to: Path | None = None
        self.problem: str | None = None

    def _new_document(self) -> tomlkit.TOMLDocument:
        doc = tomlkit.document()
        doc["version"] = self.current_version
        return doc

    def load(self) -> tomlkit.TOMLDocument:
        """Read the file, migrating it if it is older than the code.

        A missing or unreadable file gives a new document; an unreadable file is
        first moved aside. A file from a newer version is returned as it is.
        """
        self.set_aside_to = None
        self.problem = None
        try:
            raw = self.path.read_bytes()
        except FileNotFoundError:
            return self._new_document()

        doc: tomlkit.TOMLDocument | None = None
        try:
            doc = tomlkit.parse(raw.decode("utf-8-sig"))
            reason = _valid_version(doc)
        except UnicodeDecodeError:
            reason = "it is not valid UTF-8"
        except (tomlkit.exceptions.TOMLKitError, ValueError) as error:
            reason = f"it is not valid TOML ({error})"
        if reason is not None or doc is None:
            moved = self.set_aside(reason or "it could not be read")
            logger.warning(
                "Could not use %s: %s. Moved it to %s.", self.path, self.problem, moved
            )
            return self._new_document()

        version = int(doc["version"])
        if version < self.current_version:
            for n in range(version, self.current_version):
                self._migrations[n](doc)
                doc["version"] = n + 1
            self.save(doc)
        return doc

    def save(self, doc: tomlkit.TOMLDocument) -> None:
        """Write the document atomically, adding a version if it has none."""
        text = tomlkit.dumps(doc)
        if "version" not in doc:
            # tomlkit can't insert at the front of a document, so do it in text.
            text = f"version = {self.current_version}\n{text}"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self.path, text.encode("utf-8"))

    def set_aside(self, reason: str) -> Path:
        """Rename the file out of the way and return its new path."""
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = f"{self.path.stem}.unreadable-{stamp}"
        target = self.path.with_name(f"{base}.toml")
        counter = 2
        while target.exists():
            target = self.path.with_name(f"{base}-{counter}.toml")
            counter += 1
        self.path.rename(target)
        self.set_aside_to = target
        self.problem = reason
        return target
