"""A `.tla` file's content in memory: the document, its timelines and components.

The file's layout is described by the format's JSON Schema; this is what the
reader hands out and the writer takes. Kinds are lower case here ("hierarchy"),
whatever the file spells them; a kind the core doesn't know is an `UnknownKind`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

Metadata = dict[str, str | list[str]]

# Kinds as the API names them, and as the file spells them (TiLiA 0.7's spelling).
TIMELINE_KINDS: dict[str, str] = {
    "slider": "Slider",
    "hierarchy": "Hierarchy",
    "marker": "Marker",
    "beat": "Beat",
    "harmony": "Harmony",
    "range": "Range",
    "score": "Score",
    "pdf": "Pdf",
    "audiowave": "AudioWave",
}
COMPONENT_KINDS: dict[str, str] = {
    "hierarchy": "HIERARCHY",
    "marker": "MARKER",
    "range": "RANGE",
    "harmony": "HARMONY",
    "mode": "MODE",
    "beat": "BEAT",
    "pdf_marker": "PDF_MARKER",
    "note": "NOTE",
    "staff": "STAFF",
    "clef": "CLEF",
    "key_signature": "KEY_SIGNATURE",
    "time_signature": "TIME_SIGNATURE",
    "bar_line": "BAR_LINE",
    "score_annotation": "SCORE_ANNOTATION",
}
# TiLiA reads timeline kinds in any letter case, and component kinds exactly.
_TIMELINE_KINDS_IN_FILE = {
    spelling.lower(): kind for kind, spelling in TIMELINE_KINDS.items()
}
_COMPONENT_KINDS_IN_FILE = {
    spelling: kind for kind, spelling in COMPONENT_KINDS.items()
}


@dataclass(frozen=True)
class UnknownKind:
    """A timeline or component kind the core doesn't know, as the file spells it.

    It is never equal to a kind's name, so a component whose kind is spelled
    "marker" (TiLiA reads component kinds exactly, and knows "MARKER") isn't
    taken for a marker, and is written back as it was spelled.
    """

    spelling: str


Kind = str | UnknownKind


def timeline_kind_from_file(spelling: str) -> Kind:
    """The API's name for a timeline kind the file spells so, in any letter case."""
    name = spelling
    if name.endswith(_OLD_SUFFIX):
        # As TiLiA 0.7 drops it whenever it opens a file: TiLiA before 0.7
        # wrote "HIERARCHY_TIMELINE".
        name = name.replace(_OLD_SUFFIX, "")
    return _TIMELINE_KINDS_IN_FILE.get(name.lower()) or UnknownKind(spelling)


_OLD_SUFFIX = "_TIMELINE"


def timeline_kind_to_file(kind: Kind) -> str:
    """The file's spelling of a timeline kind."""
    return _to_file(kind, TIMELINE_KINDS, "timeline")


def component_kind_from_file(spelling: str) -> Kind:
    """The API's name for a component kind the file spells exactly so."""
    return _COMPONENT_KINDS_IN_FILE.get(spelling) or UnknownKind(spelling)


def component_kind_to_file(kind: Kind) -> str:
    """The file's spelling of a component kind."""
    return _to_file(kind, COMPONENT_KINDS, "component")


def _to_file(kind: Kind, spellings: dict[str, str], what: str) -> str:
    if isinstance(kind, UnknownKind):
        return kind.spelling
    if kind not in spellings:
        raise ValueError(
            f"{kind!r} isn't a {what} kind: give UnknownKind({kind!r}) for a kind"
            " the core doesn't know"
        )
    return spellings[kind]


@dataclass(frozen=True)
class ReadWarning:
    """Something the reader kept although it breaks a rule, or the migration changed."""

    place: str
    line: int | None
    message: str


@dataclass(kw_only=True)
class BeatUnit:
    """A beat unit, as stored on the beat where it starts to apply."""

    denominator: int
    units: str
    assumed: bool = False


@dataclass(kw_only=True)
class Measure:
    """A row of a beat timeline's measure table, computed from the marks on its beats."""

    id: str  # its downbeat's id
    number: int
    label: str
    beats: list[str]
    beat_unit: BeatUnit  # in force
    source: str
    beat_units: list[BeatUnit] = field(default_factory=list)  # set on its own beats
    force_display: bool = False
    cadenza: bool = False  # no pass: not counted towards its number's passes
    restart: bool = False  # the first bar of a new movement: passes count again
    next: list[str] | None = None  # downbeat ids, for folded tables
    metadata: Metadata = field(default_factory=dict)


@dataclass(kw_only=True)
class MeasureTable:
    """A beat timeline's measures, one row per measure, in time order."""

    source: str
    rows: list[Measure] = field(default_factory=list)


@dataclass(kw_only=True)
class Component:
    id: str
    kind: Kind
    attrs: dict[str, Any] = field(default_factory=dict)
    metadata: Metadata = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)  # keys the core doesn't know


@dataclass(kw_only=True)
class Timeline:
    id: str
    kind: Kind
    ordinal: int
    name: str = ""
    metadata: Metadata = field(default_factory=dict)
    attrs: dict[str, Any] = field(default_factory=dict)
    measures: MeasureTable | None = None  # beat timelines only
    components: dict[str, Component] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)  # keys the core doesn't know
    # The whole object, for a kind the core doesn't know: kept and written back as it is.
    raw: dict[str, Any] | None = None


@dataclass(kw_only=True)
class Score:
    """A score stored in the file. Its content is kept as lines, without NFC."""

    id: str
    format: str
    # Empty content is one empty line, as the text setter splits "".
    lines: list[str] = field(default_factory=lambda: [""])
    source: dict[str, str] | None = None
    license: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    @text.setter
    def text(self, value: str) -> None:
        # CRs before an LF go, so no line ends in CR, and setting the text back
        # changes nothing; a lone CR stays in its line. A final newline leaves
        # a final empty line, so the text comes back as it was. Stripping each
        # line, not a regex, keeps a long run of CRs linear.
        *lines, last = value.split("\n")
        self.lines = [line.rstrip("\r") for line in lines] + [last]


@dataclass(kw_only=True)
class Document:
    """One `.tla` file's content, in the current format, whatever version it was read from."""

    document_id: str
    format_version: str  # as read, before any migration
    time_unit: str = "seconds"
    media_path: str = ""
    media_length: float | None = None
    media_extra: dict[str, Any] = field(default_factory=dict)  # unknown keys in media
    metadata: Metadata = field(default_factory=dict)
    timelines: dict[str, Timeline] = field(default_factory=dict)
    scores: dict[str, Score] = field(default_factory=dict)
    app_name: str = "TiLiA"
    extra: dict[str, Any] = field(default_factory=dict)  # keys the core doesn't know
    warnings: list[ReadWarning] = field(default_factory=list)
    origin: Path | None = None  # where it was read from


@dataclass(frozen=True)
class Media:
    kind: str  # "local", "youtube" or "none"
    stored: str  # the media's path as the file stores it
    path: Path | None
    youtube_id: str | None
    length: float | None


@dataclass(kw_only=True)
class FileResult:
    """What migrating a folder did, or would do, to one file."""

    path: str  # relative to the folder, with "/"
    outcome: str
    from_version: str | None = None
    reason: str | None = None
    changes: dict[str, int] = field(default_factory=dict)
    warnings: list[ReadWarning] = field(default_factory=list)


@dataclass(kw_only=True)
class MigrationReport:
    files: list[FileResult] = field(default_factory=list)  # in path order
    shared_ids: list[list[str]] = field(
        default_factory=list
    )  # paths whose files share an id
