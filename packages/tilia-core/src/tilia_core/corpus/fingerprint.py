"""A file's fingerprint: the SHA-256, in lower-case hexadecimal, of the bytes the
core would write for its document (research R5).

So files that differ only in line endings, a byte-order mark or the order of
keys have the same fingerprint, on every system (FR-012). With WP3's reader,
the default, it is ``tla.fingerprint``'s.
"""

from __future__ import annotations

import os
from pathlib import Path

from .documents import DocumentReader
from .tla_reader import default_reader


def of_path(path: str | os.PathLike, reader: DocumentReader | None = None) -> str:
    """The fingerprint of the file at ``path`` as it is on disk: the value a
    scan records for the same content (FR-032), for a writer to state what it
    expects to find. Raises ``UnreadableFile`` for a file the reader refuses,
    and lets ``OSError`` through for one it can't open or read. ``reader`` is
    WP3's by default."""
    if reader is None:
        reader = default_reader()
    return reader.fingerprint(reader.read(Path(path)))
