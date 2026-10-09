"""Media files: the content types we stream, and HTTP byte ranges."""

from __future__ import annotations

import re

CONTENT_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".oga": "audio/ogg",
    ".opus": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
}

_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


class RangeNotSatisfiable(Exception):
    """The requested range lies outside the file."""


def parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """The inclusive (start, end) a ``Range`` header asks for, or None for all.

    Only one ``bytes=`` range is understood: ``a-b`` (the end is clipped to the
    file), ``a-`` or ``-n`` (the last n bytes). Any other header is ignored, as
    HTTP allows. A range outside the file raises ``RangeNotSatisfiable``.
    """
    found = _RANGE.match(header.strip()) if header else None
    if found is None:
        return None
    first, last = found.groups()
    if not first and not last:
        return None
    if not first:  # the last n bytes
        n = int(last)
        if n == 0 or size == 0:
            raise RangeNotSatisfiable
        return max(size - n, 0), size - 1
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if last and int(last) < start:  # not a valid range: ignored
        return None
    if start >= size:
        raise RangeNotSatisfiable
    return start, end
