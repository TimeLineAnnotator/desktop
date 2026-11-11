"""The index's reader of ``.tla`` files: WP3's ``tilia_core.tla``, behind the
seam of :mod:`.documents` (contracts/reader.md).

``tla.read`` reads every TiLiA version, migrating an old file in memory, and
:class:`TlaReader` maps its document onto the index's :class:`Document`. The
index parses nothing itself (constitution II).

Fingerprints are ``tla.fingerprint``'s: those of the bytes the core's writer
writes, and for an old file those of its migration with its media and PDF
paths as the file stores them, so that a move doesn't change it. A writer that
states the fingerprint the index holds then finds the file it expects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tilia_core import tla
from tilia_core.tla.model import Kind
from tilia_core.tla.reader import loads_for_fingerprint

from .documents import ComponentDoc, Document, TimelineDoc, UnreadableFile


@dataclass(frozen=True)
class TlaDocument(Document):
    """The index's document, with the core's own: ``source`` is what ``tla``
    read, for what needs more than the index's view (WP9's time map), and
    ``for_fingerprint`` the document the file's fingerprint is taken from,
    when it isn't ``source`` (an old file)."""

    source: tla.Document | None = field(default=None, compare=False, repr=False)
    for_fingerprint: tla.Document | None = field(
        default=None, compare=False, repr=False
    )


def _kind(kind: Kind) -> str:
    """The kind's name, or how the file spells a kind the core doesn't know."""
    return kind.spelling if isinstance(kind, tla.UnknownKind) else str(kind)


def _timeline(tl: tla.Timeline) -> TimelineDoc:
    return TimelineDoc(
        id=tl.id,
        kind=_kind(tl.kind),
        name=tl.name or "",
        ordinal=tl.ordinal,
        fields=dict(tl.metadata),
        attrs=dict(tl.attrs),
        components=tuple(
            ComponentDoc(
                id=c.id,
                kind=_kind(c.kind),
                attrs=dict(c.attrs),
                fields=dict(c.metadata),
            )
            for c in tl.components.values()
        ),
    )


def document_of(
    doc: tla.Document, for_fingerprint: tla.Document | None = None
) -> TlaDocument:
    """The index's view of ``doc``, its timelines in the file's order."""
    timelines = sorted(doc.timelines.values(), key=lambda tl: tl.ordinal)
    return TlaDocument(
        document_id=doc.document_id,
        format_version=doc.format_version,
        media_length=doc.media_length,
        time_unit=doc.time_unit,
        fields=dict(doc.metadata),
        timelines=tuple(_timeline(tl) for tl in timelines),
        source=doc,
        for_fingerprint=for_fingerprint,
    )


class TlaReader:
    """The index's :class:`~.documents.DocumentReader` on ``tilia_core.tla``:
    the default of ``open_corpus`` and of ``fingerprint``."""

    extensions: tuple[str, ...] = (".tla",)

    def read(self, path: Path) -> Document:
        """The file's document. Raises :class:`UnreadableFile` for content
        ``tla`` refuses, and lets ``OSError`` through."""
        with open(path, "rb") as file:
            data = file.read()
        try:
            doc = tla.loads(data, path=path)
            # A file of the current format holds its fingerprint's document;
            # an old one's is its migration with its paths as stored.
            fp = None
            if doc.format_version != tla.FORMAT_VERSION:
                fp = loads_for_fingerprint(data, path=path)
        except tla.UnreadableFile as err:
            raise UnreadableFile(Path(path), err.message, err.line) from err
        return document_of(doc, fp)

    def canonical_bytes(self, document: Document) -> bytes:
        """The bytes the file's fingerprint is taken from: ``tla``'s canonical
        bytes of the document read, or for an old file of its migration with
        its paths as stored. Raises ``TypeError`` for a document that
        :meth:`read` didn't give."""
        if not isinstance(document, TlaDocument) or document.source is None:
            raise TypeError(f"not a document read from a .tla file: {document!r}")
        return tla.canonical_bytes(document.for_fingerprint or document.source)

    def is_temporary(self, name: str) -> bool:
        """Whether ``name`` is one of ``tla.write``'s temporary files."""
        return tla.is_temporary(name)


def default_reader() -> TlaReader:
    """The reader ``open_corpus`` and ``fingerprint`` use when given none."""
    return TlaReader()


__all__ = ["TlaDocument", "TlaReader", "default_reader", "document_of"]
