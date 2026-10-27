"""A file's fingerprint: the SHA-256, in lower-case hexadecimal, of the bytes the
core would write for its document (research R5).

So files that differ only in line endings, a byte-order mark or the order of
keys have the same fingerprint, on every system (FR-012).
"""

from __future__ import annotations

import hashlib

from .documents import Document, DocumentReader


def of_document(reader: DocumentReader, document: Document) -> str:
    """The fingerprint of ``document``: the SHA-256 hex of
    ``reader.canonical_bytes(document)``."""
    return hashlib.sha256(reader.canonical_bytes(document)).hexdigest()
