"""A `.tla` file's content in memory: the document, its timelines and components.

The file's layout is described by the format's JSON Schema; this is what the
reader hands out and the writer takes. Kinds are lower case here ("hierarchy"),
whatever the file spells them; a kind the core doesn't know is an `UnknownKind`.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
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
# No AUDIOWAVE: an AudioWave timeline's amplitude bars, which TiLiA 0.x
# stored, aren't stored any more, since TiLiA computes them from the media.
# The migration drops them by their timeline's kind; in a file of the
# current format, one is a component of a kind the core doesn't know.
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
# The component kinds each timeline kind holds, as TiLiA's timelines do. A
# component of another kind is kept as it is, as one of a kind the core
# doesn't know, with a warning.
TIMELINE_COMPONENTS: dict[str, frozenset[str]] = {
    "slider": frozenset(),
    "hierarchy": frozenset({"hierarchy"}),
    "marker": frozenset({"marker"}),
    "beat": frozenset({"beat"}),
    "harmony": frozenset({"harmony", "mode"}),
    "range": frozenset({"range"}),
    # A legacy score's components (FR-022).
    "score": frozenset(
        {
            "note",
            "staff",
            "clef",
            "key_signature",
            "time_signature",
            "bar_line",
            "score_annotation",
        }
    ),
    "pdf": frozenset({"pdf_marker"}),
    "audiowave": frozenset(),
}
# TiLiA 0.7 reads timeline kinds in any letter case, and component kinds
# exactly. A file of the current format spells both as the writer writes them.
_TIMELINE_KINDS_IN_OLD_FILE = {
    spelling.lower(): kind for kind, spelling in TIMELINE_KINDS.items()
}
_TIMELINE_KINDS_IN_FILE = {spelling: kind for kind, spelling in TIMELINE_KINDS.items()}
_COMPONENT_KINDS_IN_FILE = {
    spelling: kind for kind, spelling in COMPONENT_KINDS.items()
}


@dataclass(frozen=True)
class UnknownKind:
    """A timeline or component kind the core doesn't know, as the file spells it.

    It is never equal to a kind's name, so a component whose kind is spelled
    "marker" (TiLiA reads component kinds exactly, and knows "MARKER") isn't
    taken for a marker, and is written back as it was spelled. The writer
    refuses one spelled as the reader reads a known kind: a timeline's
    "Marker", or a component's "MARKER" in a timeline that holds markers. In
    another timeline, a component spelled "MARKER" is read as an UnknownKind.
    """

    spelling: str


Kind = str | UnknownKind


def timeline_kind_from_current_file(spelling: str) -> Kind:
    """The API's name for a timeline kind a file of the current format spells
    exactly so, as the writer writes it. In another letter case, or with the
    suffix of TiLiA before 0.7, the kind is one the core doesn't know."""
    return _TIMELINE_KINDS_IN_FILE.get(spelling) or UnknownKind(spelling)


def timeline_kind_from_file(spelling: str) -> Kind:
    """The API's name for a timeline kind an old file spells so, in any letter
    case, as TiLiA 0.7 reads it: what the migration reads."""
    name = spelling
    if name.endswith(_OLD_SUFFIX):
        # As TiLiA 0.7 drops it whenever it opens a file: TiLiA before 0.7
        # wrote "HIERARCHY_TIMELINE".
        name = name.replace(_OLD_SUFFIX, "")
    return _TIMELINE_KINDS_IN_OLD_FILE.get(name.lower()) or UnknownKind(spelling)


_OLD_SUFFIX = "_TIMELINE"


def timeline_kind_to_file(kind: Kind) -> str:
    """The file's spelling of a timeline kind."""
    return _to_file(kind, TIMELINE_KINDS, timeline_kind_from_current_file, "timeline")


def component_kind_from_file(spelling: str) -> Kind:
    """The API's name for a component kind the file spells exactly so."""
    return _COMPONENT_KINDS_IN_FILE.get(spelling) or UnknownKind(spelling)


def component_kind_to_file(kind: Kind) -> str:
    """The file's spelling of a component kind."""
    return _to_file(kind, COMPONENT_KINDS, component_kind_from_file, "component")


def _to_file(
    kind: Kind,
    spellings: dict[str, str],
    from_file: Callable[[str], Kind],
    what: str,
) -> str:
    if isinstance(kind, UnknownKind):
        # One the reader would read back as a known kind wouldn't stay unknown.
        known = from_file(kind.spelling)
        if not isinstance(known, UnknownKind):
            raise ValueError(
                f"{kind!r} would be read back as the {what} kind {known!r}:"
                f" give {known!r}"
            )
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

    def __str__(self) -> str:
        """As an `UnreadableFile` reads: the line when known, then the message."""
        if self.line is None:
            return self.message
        return f"line {self.line}: {self.message}"


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
    # The first measure of a new movement or song, its pickup if it has one:
    # passes count again.
    restart: bool = False
    next: list[str] | None = None  # downbeat ids, for folded tables
    metadata: Metadata = field(default_factory=dict)


@dataclass(kw_only=True)
class MeasureTable:
    """A beat timeline's measures, one row per measure, in time order."""

    source: str
    rows: list[Measure] = field(default_factory=list)


@dataclass(kw_only=True)
class Component:
    """A timeline's component. `attrs` are its kind's attributes, with the
    schema's defaults filled in when it is read, except those derived from
    another value: a `pre_start` or `post_end` the file doesn't have stays
    unset and follows `start` or `end`, so code that reads it falls back to
    `start` or `end`. Once set, it is written whatever its value.

    A null in a file is a missing key: it is read as the key's default
    (`"label": null` as `""`), or leaves the key unset when it has none (a
    beat's `"measure": null` is no mark), and is never written back. None
    given for a key is likewise left out when written. A legacy score's
    components keep their attributes as they are, nulls included."""

    id: str
    kind: Kind
    attrs: dict[str, Any] = field(default_factory=dict)
    metadata: Metadata = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)  # keys the core doesn't know

    # A component of a kind the core doesn't know is kept as it is: this says
    # whether its file had "metadata", so that the writer writes an empty one
    # back where it was, and only there. The reader sets it. A field, so that
    # dataclasses.replace keeps it, but not shown or compared.
    _metadata_in_file: bool = field(default=False, repr=False, compare=False)


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
    # The whole object, for a kind the core doesn't know: kept and written back as it is,
    # except its name, ordinal and metadata, which are written from the fields above,
    # not from `raw`: change those, since a change to raw's copies isn't saved.
    raw: dict[str, Any] | None = None


# A beat timeline's measure table, built from the marks on its beats
# (contracts/layout.md, *Beat timelines and their measures*). The reader builds
# it when it reads a file, and `measure_table` builds it again from a timeline
# as it is after a change in memory; the writer never writes it.
#
# For the code that edits beats, TiLiA (WP6) and the bulk edits (WP14): when a
# downbeat is deleted, its mark moves to the next beat, and every `next` that
# named it must name the new downbeat; adding or deleting other beats changes
# no `next`. A measure a person edits (moves, adds or deletes one of its beats,
# or changes its number, label or beat unit) gets the source "edited", unless
# its source is "tapped", which stays; moving a downbeat edits two measures,
# the one it starts and the one before.


def measure_table(timeline: Timeline) -> MeasureTable | None:
    """A beat timeline's measure table, from the marks on its beats as they
    are now; None for a timeline of another kind."""
    if timeline.kind != "beat":
        return None
    source = timeline.attrs.get("measure_source")
    if not isinstance(source, str):
        source = _default_measure_source()
    beats = {
        key: component.attrs
        for key, component in timeline.components.items()
        if component.kind == "beat"
    }
    return MeasureTable(source=source, rows=measures_of(beats, source))


def _default_measure_source() -> str:
    # The schema's, which the layout reads; imported here, since the layout
    # imports this module.
    from tilia_core.tla.layout import TIMELINE_SHAPES

    return TIMELINE_SHAPES["beat"].defaults["measure_source"]


def beat_order(beats: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """The ids of a beat timeline's beats, each given with its attributes, in
    their order: by time, beats at the same time in id order, then the beats
    without a time, in id order. TiLiA never writes a beat without a time;
    the reader keeps one, with a warning
    (TimeLineAnnotator/project-management#285)."""
    timed: list[tuple[int | float, str]] = []
    untimed: list[str] = []
    for beat_id, attrs in beats.items():
        time = attrs.get("time")
        if _is_time(time):
            timed.append((time, beat_id))
        else:
            untimed.append(beat_id)
    return [beat_id for _, beat_id in sorted(timed)] + sorted(untimed)


def _is_time(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return not isinstance(value, float) or math.isfinite(value)


def measures_of(beats: Mapping[str, Mapping[str, Any]], source: str) -> list[Measure]:
    """The rows of a beat timeline's measure table, from its beats, each given
    by id with its attributes, and the table's `source`.

    A row for each beat with a `measure` mark, in the beats' order
    (`beat_order`), identified by its downbeat's id. Its number is the mark's,
    else the previous row's plus one, and the first row's 1; its label the
    mark's, else its number as text; its source the mark's, else the table's.
    Its beats run from its downbeat to the next mark, without a tap on a
    closing barline, which is the barline, not a beat
    (TimeLineAnnotator/project-management#332). Its `beat_units` are those
    set on its beats that desktop#621 can read, and `beat_unit` is the unit
    in force, as WP9's meters take it: the first set in the measure, else
    the one carried from the measures before; a movement whose first measure
    has none takes, assumed, the first set in the movement, else the one in
    force before it, else 4 / "1".
    """
    from tilia_core.timemap import units  # here: the time map imports this package

    default = BeatUnit(
        denominator=units.DEFAULT_DENOMINATOR, units=units.DEFAULT_UNITS, assumed=True
    )
    rows: list[Measure] = []
    for beat_id in beat_order(beats):
        attrs = beats[beat_id]
        if attrs.get("closing"):
            continue
        mark = attrs.get("measure")
        if isinstance(mark, dict):
            rows.append(_measure(beat_id, mark, rows, source, default))
        if rows:
            rows[-1].beats.append(beat_id)
            unit = readable_beat_unit(attrs.get("beat_unit"))
            if unit is not None:
                rows[-1].beat_units.append(unit)
    _set_units_in_force(rows, default)
    return rows


def _measure(
    beat_id: str,
    mark: Mapping[str, Any],
    rows: list[Measure],
    source: str,
    default: BeatUnit,
) -> Measure:
    number = mark.get("number")
    if isinstance(number, float) and number.is_integer():
        number = int(number)
    if isinstance(number, bool) or not isinstance(number, int):
        number = rows[-1].number + 1 if rows else 1
    label = mark.get("label")
    own_source = mark.get("source")
    following = mark.get("next")
    metadata = mark.get("metadata")
    return Measure(
        id=beat_id,
        number=number,
        label=label if isinstance(label, str) else str(number),
        beats=[],
        beat_unit=default,
        source=own_source if isinstance(own_source, str) else source,
        force_display=bool(mark.get("force_display")),
        cadenza=bool(mark.get("cadenza")),
        restart=bool(mark.get("restart")),
        next=list(following) if isinstance(following, list) else None,
        metadata=copy.deepcopy(metadata) if isinstance(metadata, dict) else {},
    )


def _set_units_in_force(rows: list[Measure], default: BeatUnit) -> None:
    governing: BeatUnit | None = None
    for movement in _movements(rows):
        first = next((unit for row in movement for unit in row.beat_units), None)
        carried = first or governing
        governing = default if carried is None else replace(carried, assumed=True)
        for row in movement:
            if row.beat_units:
                governing = row.beat_units[0]
            row.beat_unit = replace(governing)


def _movements(rows: list[Measure]) -> Iterator[list[Measure]]:
    """The rows by movement: one starts at the first row and at each restart."""
    movement: list[Measure] = []
    for row in rows:
        if row.restart and movement:
            yield movement
            movement = []
        movement.append(row)
    if movement:
        yield movement


def beat_unit_problems(value: Mapping[str, Any]) -> list[str]:
    """The keys of a stored beat unit whose values desktop#621 can't read:
    `units` it can't parse, a `denominator` that isn't from 1 to 128."""
    from tilia_core.timemap import units  # here: the time map imports this package

    problems = []
    text = value.get("units")
    if not isinstance(text, str) or not units.parse_units(text).is_valid:
        problems.append("units")
    if not units.validate_denominator(value.get("denominator")):
        problems.append("denominator")
    return problems


def readable_beat_unit(value: Any) -> BeatUnit | None:
    """A stored beat unit, if desktop#621 can read it; else None, as TiLiA
    drops one it can't read when it loads a file."""
    if not isinstance(value, Mapping) or beat_unit_problems(value):
        return None
    return BeatUnit(
        denominator=value["denominator"],
        units=value["units"],
        assumed=bool(value.get("assumed")),
    )


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
