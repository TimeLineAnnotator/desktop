"""A file's fingerprint: the SHA-256, in lower-case hexadecimal, of the bytes the
core would write for its document (research R5).

So files that differ only in line endings, a byte-order mark or the order of
keys have the same fingerprint, on every system (FR-012).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .documents import Document, DocumentReader

NO_READER = "no .tla reader yet: TimeLineAnnotator/project-management#7"


def of_document(reader: DocumentReader, document: Document) -> str:
    """The fingerprint of ``document``: the SHA-256 hex of
    ``reader.canonical_bytes(document)``."""
    return hashlib.sha256(reader.canonical_bytes(document)).hexdigest()


def of_path(path: str | os.PathLike, reader: DocumentReader | None = None) -> str:
    """The fingerprint of the file at ``path`` as it is on disk: the value a
    scan records for the same content (FR-032), for a writer to state what it
    expects to find. Raises ``UnreadableFile`` for a file the reader refuses,
    and lets ``OSError`` through for one it can't open or read. Until WP3
    lands there is no default reader: ``reader=None`` raises
    ``NotImplementedError``."""
    if reader is None:
        raise NotImplementedError(NO_READER)
    return of_document(reader, reader.read(Path(path)))
