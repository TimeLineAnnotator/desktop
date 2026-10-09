"""The errors of reading and writing `.tla` files."""

from __future__ import annotations

import os
from pathlib import Path


def printable(text: str) -> str:
    """`text` with each lone surrogate written as its escape (`\\ud83d`), so that
    it can be printed and encoded: a key cut inside an emoji holds one, and so
    does a file name that isn't UTF-8 on Linux."""
    return text.encode("utf-8", "backslashreplace").decode("utf-8")


class UnreadableFile(ValueError):
    """A file whose content the reader refuses.

    `message` is for users ("not valid JSON (...)", "empty file", "not a TiLiA
    file"). `line` is where JSON parsing stopped, or where `place` is in the
    file, when known. `place` is a JSON Pointer (RFC 6901) to what is wrong.
    """

    def __init__(
        self,
        message: str,
        *,
        path: str | os.PathLike[str] | None = None,
        line: int | None = None,
        place: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.path = None if path is None else Path(path)
        self.line = line
        self.place = place

    def __str__(self) -> str:
        where = []
        if self.path is not None and self.path.name:
            where.append(printable(self.path.name))
        if self.line is not None:
            where.append(f"line {self.line}")
        if not where:
            return self.message
        return f"{', '.join(where)}: {self.message}"


class FileChanged(Exception):
    """The file on disk isn't the version the caller expected to replace.

    `expected` is the fingerprint the caller stated, or None when no file was
    expected. `found` is the fingerprint on disk, or None when the file is
    missing or can't be read.
    """

    def __init__(
        self, path: str | os.PathLike[str], expected: str | None, found: str | None
    ) -> None:
        self.path = Path(path)
        super().__init__(self.path, expected, found)
        self.expected = expected
        self.found = found

    def __str__(self) -> str:
        name = printable(self.path.name)
        if self.expected is None:
            return f"{name} already exists"
        if self.found is None:
            return f"{name} was removed or became unreadable after it was read"
        return f"{name} has changed since it was read"
