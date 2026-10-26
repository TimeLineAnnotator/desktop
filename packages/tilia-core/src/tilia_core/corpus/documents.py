"""What the index reads from a file: the seam with the format's reader.

The index never parses a ``.tla`` file itself. It asks a :class:`DocumentReader`
for a :class:`Document`, maps the document to rows, and asks the reader for the
bytes the core would write, for fingerprints. WP3 (the format in the core,
TimeLineAnnotator/project-management#7) provides the reader; until it lands,
only tests read files, through a stand-in of their own.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ComponentDoc:
    """A component as the file stores it.

    ``kind`` is ``hierarchy``, ``marker``, ``range``, ``harmony`` (a chord),
    ``mode`` (a key), ``beat``, or the kind of a component the index doesn't
    read. ``attrs`` are the kind's own attributes, as the format names them;
    ``fields`` are its tags, ``generated_by`` and users' own fields."""

    id: str
    kind: str
    attrs: Mapping[str, Any]
    fields: Mapping[str, str | Sequence[str]]


@dataclass(frozen=True)
class TimelineDoc:
    """A timeline as the file stores it, with its components in the file's
    order.

    ``kind`` is ``hierarchy``, ``marker``, ``range``, ``harmony``, ``beat``,
    ``score``, ``pdf``, ``audiowave``, ``slider``, or the name a kind the core
    doesn't know has in the file. ``ordinal`` is its place, from 1. ``fields``
    hold ``role``, ``author``, ``tags``, ``vocabulary``, ``generated_by`` and
    users' own; ``attrs`` the kind's own attributes (a range timeline's
    ``rows``, a beat timeline's measures)."""

    id: str
    kind: str
    name: str
    ordinal: int
    fields: Mapping[str, str | Sequence[str]]
    attrs: Mapping[str, Any]
    components: Sequence[ComponentDoc]


@dataclass(frozen=True)
class Document:
    """A file as the reader gives it.

    ``document_id`` is the id the file stores, or, for an old file, the one
    derived from its content. ``format_version`` is the version the file was
    written in, before any migration in memory. ``media_length`` is in seconds
    (None without one), ``time_unit`` is ``seconds`` or ``quarters``, and
    ``fields`` are the file's fields and metadata, by the names they are
    stored under."""

    document_id: str
    format_version: str
    media_length: float | None
    time_unit: str
    fields: Mapping[str, str | Sequence[str]]
    timelines: Sequence[TimelineDoc]


class UnreadableFile(Exception):
    """A file the reader refuses: broken JSON, a newer format version, or any
    other content it can't read. ``line`` is where reading stopped, when the
    reader knows it; ``message`` is for users. A file the reader can't open or
    read raises the system's ``OSError`` instead."""

    def __init__(self, path: Path, message: str, line: int | None = None) -> None:
        self.path = path
        self.line = line
        self.message = message
        where = f" (line {line})" if line is not None else ""
        super().__init__(f"can't read{where}: {message}")


class DocumentReader(Protocol):
    """Reads documents from files, for the index.

    ``read`` never writes. It raises :class:`UnreadableFile` for content it
    refuses, and lets ``OSError`` through when it can't open or read the file.
    ``canonical_bytes`` gives, for any document, the bytes the core's writer
    would write for it. ``is_temporary`` tells the writer's temporary files,
    next to a file it is writing, which the index never reads.
    ``extensions`` are the file name endings the reader takes."""

    extensions: tuple[str, ...]

    def read(self, path: Path) -> Document:
        ...

    def canonical_bytes(self, document: Document) -> bytes:
        ...

    def is_temporary(self, name: str) -> bool:
        ...
