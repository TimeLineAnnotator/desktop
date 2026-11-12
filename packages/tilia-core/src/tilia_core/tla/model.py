"""A `.tla` file's content in memory: the document, its timelines and components.

The file's layout is described by the format's JSON Schema; this is what the
reader hands out and the writer takes. Kinds are lower case here ("hierarchy"),
whatever the file spells them; a kind the core doesn't know is an `UnknownKind`.
"""

from __future__ import annotations

import copy
import enum
import math
import threading
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol, TypeVar

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
    """Something the reader kept although it breaks a rule, or the migration changed.

    `timeline_id` and `component_id` are the document's ids of what it concerns,
    or None where there is none, such as for a component the migration dropped.
    A migration's `place` can't say: it is in the old file, with the old ids.
    """

    place: str
    line: int | None
    message: str
    timeline_id: str | None = None
    component_id: str | None = None

    def __str__(self) -> str:
        """As an `UnreadableFile` reads: the line when known, then the message."""
        if self.line is None:
            return self.message
        return f"line {self.line}: {self.message}"


@dataclass(frozen=True, kw_only=True)
class ReadProblem:
    """A broken rule for a valid component, and what it is about as it was
    found: what the writer compares what it would write with (FR-054).

    `code` says which rule it is, and `reason` what the rule says of it, which
    quotes values and reads otherwise when they change: only a warning reads it.
    `place` says what it is about: a component, a row or a value, by id, as a
    JSON Pointer, never by a position, which an edit elsewhere can change.
    `pointer` is the JSON Pointer that a warning names, when it isn't the place:
    a row's, by its position in the file. `state` is everything it holds, as a
    text. `others` are the other components a warning names, each as a place and
    a state, and `more` is how many others it is about that aren't among them.
    `joined` is, for a join, the range it joins, the same way: what the problem
    is between, where `others` are what comes next in its row. `warned` says that
    the reader has a warning of the check's for it, in the check's words, so that
    it adds none.
    """

    code: str
    reason: str
    place: str
    state: str
    pointer: str = ""
    others: tuple[tuple[str, str], ...] = ()
    joined: tuple[str, str] | None = None
    more: int = 0
    warned: bool = False


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


def measure_beats(
    beats: Mapping[str, Mapping[str, Any]], order: list[str] | None = None
) -> list[list[str]]:
    """The beats of each measure, by id, in the beats' order (`beat_order`,
    unless `order` gives it): from each beat with a `measure` mark to the
    next. In no measure: a tap on a closing barline, which is the barline,
    not a beat (TimeLineAnnotator/project-management#332); a beat without a
    time, whose measure isn't known, so that a downbeat without one starts
    none, as the time map reads its rows; and the beats before the first
    mark."""
    groups: list[list[str]] = []
    for beat_id in beat_order(beats) if order is None else order:
        attrs = beats[beat_id]
        if attrs.get("closing") or not _is_time(attrs.get("time")):
            continue
        if isinstance(attrs.get("measure"), dict):
            groups.append([])
        if groups:
            groups[-1].append(beat_id)
    return groups


def measure_numbers(marks: Iterable[Mapping[str, Any]]) -> Iterator[tuple[int, str]]:
    """Each measure's number and label, from the marks in their order: the
    mark's number, else the previous measure's plus one, and the first
    measure's 1; the mark's label, else the number as text."""
    previous: int | None = None
    for mark in marks:
        number = mark.get("number")
        if isinstance(number, float) and number.is_integer():
            number = int(number)
        if isinstance(number, bool) or not isinstance(number, int):
            number = 1 if previous is None else previous + 1
        label = mark.get("label")
        yield number, label if isinstance(label, str) else str(number)
        previous = number


def measures_of(beats: Mapping[str, Mapping[str, Any]], source: str) -> list[Measure]:
    """The rows of a beat timeline's measure table, from its beats, each given
    by id with its attributes, and the table's `source`.

    A row for each measure (`measure_beats`), identified by its downbeat's
    id, numbered and labelled by `measure_numbers`; its source the mark's,
    else the table's. Its `next` names rows: a downbeat the mark's `next`
    names that starts no row, one without a time, is left out of it, and
    kept in the file. Its `beat_units` are those set on its beats that
    desktop#621 can read, and `beat_unit` is the unit in force, as WP9's
    meters take it (`units_in_force`): the first set in the measure, else the
    one carried from the measures before; a movement whose first measure has
    none takes, assumed, the first set in the movement, else the one in force
    before it, else 4 / "1".
    """
    from tilia_core.timemap import units  # here: the time map imports this package

    default = BeatUnit(
        denominator=units.DEFAULT_DENOMINATOR, units=units.DEFAULT_UNITS, assumed=True
    )
    groups = measure_beats(beats)
    marks = [beats[group[0]]["measure"] for group in groups]
    starts = {group[0] for group in groups}
    rows: list[Measure] = []
    for group, mark, (number, label) in zip(
        groups, marks, measure_numbers(marks), strict=True
    ):
        row = _measure(group[0], mark, number, label, source, default)
        if row.next is not None:
            row.next = [downbeat for downbeat in row.next if downbeat in starts]
        row.beats = group
        for beat_id in group:
            unit = readable_beat_unit(beats[beat_id].get("beat_unit"))
            if unit is not None:
                row.beat_units.append(unit)
        rows.append(row)
    _set_units_in_force(rows, default)
    return rows


def _measure(
    beat_id: str,
    mark: Mapping[str, Any],
    number: int,
    label: str,
    source: str,
    default: BeatUnit,
) -> Measure:
    own_source = mark.get("source")
    following = mark.get("next")
    metadata = mark.get("metadata")
    return Measure(
        id=beat_id,
        number=number,
        label=label,
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
    for movement in units_in_force(rows, _beat_units, default, _assumed):
        for row, unit in movement:
            row.beat_unit = replace(unit)


def _beat_units(row: Measure) -> list[BeatUnit]:
    return row.beat_units


def _assumed(unit: BeatUnit) -> BeatUnit:
    return replace(unit, assumed=True)


class _Restarts(Protocol):
    """A measure, as `units_in_force` reads it: whether it is marked `restart`."""

    @property
    def restart(self) -> bool:
        ...


_Row = TypeVar("_Row", bound=_Restarts)
_Unit = TypeVar("_Unit")


def units_in_force(
    rows: Iterable[_Row],
    units_of: Callable[[_Row], Sequence[_Unit]],
    default: _Unit,
    assumed: Callable[[_Unit], _Unit],
) -> Iterator[list[tuple[_Row, _Unit]]]:
    """Each measure with the beat unit in force in it, by movement, as WP3's
    table and WP9's meters both take it: desktop#621's
    `BeatTimeline._compute_measure_meters`, with movements. `units_of` gives
    the units set on a measure's beats that desktop#621 can read, in beat
    order.

    The first unit set in a measure governs it and is carried forward. A
    movement starts at the first measure and at each restart, and always
    starts with a unit: where its first measure has none, it takes the first
    set in the movement, else the one in force before it, as `assumed` makes
    it; else `default`. No unit reaches back across a restart.
    """
    governing: _Unit | None = None
    for movement in _movements(rows):
        first = next((unit for row in movement for unit in units_of(row)), None)
        carried = first if first is not None else governing
        governing = default if carried is None else assumed(carried)
        in_force: list[tuple[_Row, _Unit]] = []
        for row in movement:
            units = units_of(row)
            if units:
                governing = units[0]
            in_force.append((row, governing))
        yield in_force


def _movements(rows: Iterable[_Row]) -> Iterator[list[_Row]]:
    """The rows by movement: one starts at the first row and at each restart."""
    movement: list[_Row] = []
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


TIME_MAP_ROLE = "time_map"


def claims_time_map(role: object) -> bool:
    """Whether a timeline whose role is `role` claims the role time_map: its
    role is that, or a list that holds it. The check's warning about a
    second beat timeline that claims it, and the time map's choice, read it
    so."""
    if isinstance(role, (list, tuple)):
        return TIME_MAP_ROLE in role
    return role == TIME_MAP_ROLE


def score_lines(text: str) -> list[str]:
    """A score's content as the file stores it: its lines, without NFC.

    CRs before an LF go, so no line ends in CR, and splitting the joined
    lines again gives the same lines; a lone CR stays in its line. A final newline
    leaves a final empty line, so joining the lines with LF gives the text
    back, with LF for CRLF. Stripping each line, not a regex, keeps a long
    run of CRs linear.
    """
    *lines, last = text.split("\n")
    return [line.rstrip("\r") for line in lines] + [last]


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
        # Setting the text back changes nothing.
        self.lines = score_lines(value)


class _MadeWhenAsked:
    """A document's fingerprint, made by `make` the first time it is asked for,
    once, whichever thread asks first. `make` holds the bytes the document was
    read from, and is dropped once it has made it."""

    def __init__(self, make: Callable[[], str]) -> None:
        self._make: Callable[[], str] | None = make
        self._made: str | None = None
        self._lock = threading.Lock()

    def get(self) -> str:
        with self._lock:
            if self._make is not None:
                self._made = self._make()
                self._make = None  # it holds the file's bytes
            assert self._made is not None
            return self._made

    def made(self) -> str | None:
        """The fingerprint once it is made; None before, without making it."""
        with self._lock:
            return self._made if self._make is None else None

    def __deepcopy__(self, memo: dict[int, Any]) -> str:
        # As `dataclasses.asdict` copies it: what it holds, the same in any
        # process, where the object would show its address.
        return self.get()

    def __reduce__(self) -> tuple[Any, ...]:
        # A lock doesn't pickle or copy: the fingerprint once made, else a new one.
        with self._lock:
            if self._make is None:
                return (str, (self._made,))
            return (_MadeWhenAsked, (self._make,))


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
    origin: Path | None = None  # where it was read from, or last written to
    # `fingerprint`'s, which a read makes when it is first asked for.
    _fingerprint: str | _MadeWhenAsked | None = field(
        default=None, repr=False, compare=False
    )
    # The plain SHA-256 of the bytes it was read from, whose fingerprint is
    # `fingerprint`: a file that still has them is unchanged, and a write that
    # states that fingerprint needn't read it as a document again, which for an
    # old file would migrate it again. None once `fingerprint` is set otherwise.
    _read_digest: str | None = field(default=None, repr=False, compare=False)
    # What it broke when it was read, or last written: the writer writes these
    # back while what they are about hasn't changed (FR-054). A document made
    # in memory has nothing read to keep.
    read_problems: list[ReadProblem] = field(
        default_factory=list, repr=False, compare=False
    )
    # When it had no media length: each component's state, by its place, as in a
    # `ReadProblem`. Its times weren't compared with any, so one past a length
    # given since is no new problem while it hasn't changed.
    read_unmeasured: dict[str, str] = field(
        default_factory=dict, repr=False, compare=False
    )

    @property
    def fingerprint(self) -> str | None:
        """The fingerprint of the file as read or last written, for a write to
        state (FR-043). For a document read, it is made the first time it is
        asked for, from the bytes read, which the document keeps until then: the
        file isn't read again. An old file's isn't `fingerprint_of` the document.
        None for a document built in memory, which a write then checks nothing
        for. Never written, and not what a document holds: it isn't compared."""
        value = self._fingerprint
        return value.get() if isinstance(value, _MadeWhenAsked) else value

    @fingerprint.setter
    def fingerprint(self, value: str | None) -> None:
        self._fingerprint = value
        self._read_digest = None  # no longer the bytes of that fingerprint


@dataclass(frozen=True)
class Media:
    kind: str  # "local", "youtube" or "none"
    stored: str  # the media's path as the file stores it
    path: Path | None
    youtube_id: str | None
    length: float | None


class Outcome(str, enum.Enum):
    """What migrating a folder did, or would do, to one file."""

    WOULD_MIGRATE = "would_migrate"  # an old file, without `apply`
    MIGRATED = "migrated"
    CURRENT = "current"
    NEWER = "newer"  # of a newer format, which this core can't migrate
    UNREADABLE = "unreadable"
    CHANGED_SINCE_READ = "changed_since_read"
    IN_USE = "in_use"  # another program held it open
    WRITE_FAILED = "write_failed"


# The outcomes of a file the migration should have written, and didn't.
LEFT_ALONE_ON_FAILURE = frozenset(
    {
        Outcome.UNREADABLE,
        Outcome.CHANGED_SINCE_READ,
        Outcome.IN_USE,
        Outcome.WRITE_FAILED,
    }
)


@dataclass(kw_only=True)
class FileResult:
    """What migrating a folder did, or would do, to one file.

    `path` is the file's path relative to the folder, with "/", as the
    system names it. `reason` says why a file was left alone, for users.
    `changes` counts what the migration dropped or changed, and `warnings`
    are the rules the migrated file breaks, which don't stop it being
    migrated; the migration's own warnings are what `changes` counts.
    `traceback` is the traceback of an error in the core that left the file
    alone, one that reading or writing doesn't otherwise raise, as Python
    prints it: text, which holds none of the frames the error went through,
    nor what they held.
    """

    path: str
    outcome: Outcome
    from_version: str | None = None
    reason: str | None = None
    changes: dict[str, int] = field(default_factory=dict)
    warnings: list[ReadWarning] = field(default_factory=list)
    traceback: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class FolderNotListed:
    """A folder below the one migrated that couldn't be listed: no file in
    it was found, so no old file in it was migrated."""

    path: str  # relative to the folder, with "/", ending in "/"
    reason: str


@dataclass(kw_only=True)
class MigrationReport:
    files: list[FileResult] = field(default_factory=list)  # in path order
    shared_ids: list[list[str]] = field(
        default_factory=list
    )  # paths whose files share an id
    folders_not_listed: list[FolderNotListed] = field(default_factory=list)

    @property
    def status(self) -> int:
        """`tilia migrate`'s exit status: 1 when it left alone a file it
        should have migrated, or a folder it couldn't list, else 0. A file
        of a newer format isn't one: this core can't migrate it, and nothing
        failed."""
        failed = any(Outcome(f.outcome) in LEFT_ALONE_ON_FAILURE for f in self.files)
        return 1 if failed or self.folders_not_listed else 0
