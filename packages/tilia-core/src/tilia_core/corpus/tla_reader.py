"""The index's reader of ``.tla`` files: WP3's ``tilia_core.tla``, behind the
seam of :mod:`.documents` (contracts/reader.md).

``tla.read`` reads every TiLiA version, migrating an old file in memory, and
:class:`TlaReader` maps its document onto the index's :class:`Document`. The
index parses nothing itself (constitution II).

Fingerprints are ``tla.fingerprint``'s: those of the bytes the core's writer
writes, and for an old file those of its migration with its media and PDF
paths as the file stores them, so that a move doesn't change it. A writer that
states the fingerprint the index holds then finds the file it expects. The
reader takes it from the document read, which then holds none of the file's
bytes (TimeLineAnnotator/project-management#545): the scan's workers pickle
the documents back, and the scan holds many at once.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from tilia_core import timemap, tla
from tilia_core.tla.model import Kind
from tilia_core.tla.problems import unmeasured

from .documents import ComponentDoc, Document, TimelineDoc, UnreadableFile
from .time_map import TimeMapFound


@dataclass(frozen=True)
class TlaDocument(Document):
    """The index's document, with the core's own: ``source`` is what ``tla``
    read, for what needs more than the index's view (WP9's time map), and
    ``fingerprint`` the one it was read with."""

    source: tla.Document | None = field(default=None, compare=False, repr=False)
    fingerprint: str | None = field(default=None, compare=False)


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


def document_of(doc: tla.Document, fingerprint: str | None = None) -> TlaDocument:
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
        fingerprint=fingerprint,
    )


class TlaReader:
    """The index's :class:`~.documents.DocumentReader` on ``tilia_core.tla``:
    the default of ``open_corpus`` and of ``fingerprint``."""

    extensions: tuple[str, ...] = (".tla",)

    def read(self, path: Path) -> Document:
        """The file's document, with the fingerprint it was read with. Raises
        :class:`UnreadableFile` for content ``tla`` refuses, and lets
        ``OSError`` through.

        ``tla`` keeps the bytes read in the document, for what a write states
        and compares, until each is first asked for
        (TimeLineAnnotator/project-management#533): its fingerprint, and its
        components' states when it has no media length. Both are made here, so
        that the document holds no bytes, without reading the file as a
        document again where it can be helped."""
        with open(path, "rb") as file:
            data = file.read()
        try:
            doc = tla.loads(data, path=path)
            if doc.format_version == tla.FORMAT_VERSION:
                # Its fingerprint is that of the document read; asking for it
                # would read the bytes again.
                doc.fingerprint = tla.fingerprint_of(doc)
            # An old file's is that of its migration with its paths as stored,
            # which tla makes from the bytes.
            fingerprint = doc.fingerprint
            # As tla would make them from the bytes, which give this document.
            doc.read_unmeasured = unmeasured(doc)
        except tla.UnreadableFile as err:
            raise UnreadableFile(Path(path), err.message, err.line) from err
        return document_of(doc, fingerprint)

    def fingerprint(self, document: Document) -> str:
        """The fingerprint ``document`` was read with, ``tla.fingerprint``'s.
        Raises ``TypeError`` for a document that :meth:`read` didn't give."""
        if not isinstance(document, TlaDocument) or document.fingerprint is None:
            raise TypeError(f"not a document read from a .tla file: {document!r}")
        return document.fingerprint

    def is_temporary(self, name: str) -> bool:
        """Whether ``name`` is one of ``tla.write``'s temporary files."""
        return tla.is_temporary(name)


def default_reader() -> TlaReader:
    """The reader ``open_corpus`` and ``fingerprint`` use when given none."""
    return TlaReader()


def find_time_map(document: Document, roles: Mapping[str, str | None]) -> TimeMapFound:
    """The file's time map as WP9's ``find_time_map`` chooses it, with the
    roles the index resolved (contracts/time-map.md), and why it has none and
    WP9's warnings (WP9's FR-082): the default of ``open_corpus``. No time map,
    reason or warning for a document :class:`TlaReader` didn't give."""
    if not isinstance(document, TlaDocument) or document.source is None:
        return TimeMapFound(time_map=None)
    chosen = timemap.find_time_map(document.source, roles)
    return TimeMapFound(
        time_map=chosen.time_map, reason=chosen.reason, warnings=chosen.warnings
    )


def time_map_of(
    document: Document, roles: Mapping[str, str | None]
) -> timemap.TimeMap | None:
    """The file's time map as :func:`find_time_map` chooses it, without its
    reason or warnings. None for a document :class:`TlaReader` didn't give,
    and for one without a time map."""
    return find_time_map(document, roles).time_map


__all__ = [
    "TlaDocument",
    "TlaReader",
    "default_reader",
    "document_of",
    "find_time_map",
    "time_map_of",
]
