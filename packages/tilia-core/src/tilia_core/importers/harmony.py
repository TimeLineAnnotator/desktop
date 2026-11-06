"""Chords and keys from a CSV with times, and TiLiA's reading of their symbols, moved
into the core.

The symbols are read with music21, which only the `harmony` extra installs, so it is
imported inside the functions that read them, never when this module is imported.

A row is read as TiLiA reads it, one after the other: a chord's numeral in the key in
force among the keys of the rows before it, and each key then updating the `applied_to`
of the chords of those rows. Only the keys the rules keep count, since in TiLiA a
refused key never enters the timeline, so the keys are checked first. The whole
timeline is then checked once, just before it is committed.
"""

from __future__ import annotations

import bisect
import importlib.util
import logging
import math
import os
import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from tilia_core import rules, tla
from tilia_core.importers._commit import commit
from tilia_core.importers._csv import CsvRow, read_csv
from tilia_core.importers._results import ImportFailed, ImportResult, RowProblem
from tilia_core.tla.errors import printable
from tilia_core.tla.layout import COMPONENT_SHAPES

if TYPE_CHECKING:
    import music21

logger = logging.getLogger(__name__)

# TiLiA's texts: tilia/parsers/csv/base.py's, and tilia/errors.py's for a timeline
# added before the length is known. A file can bring a timeline with no length,
# which is the same state (TimeLineAnnotator/project-management#418).
_COLUMN_NOT_FOUND = "Column '{}' not found on first row of .csv file."
_NO_MEDIA_LENGTH = (
    "No media loaded and no duration set. Load a media file with 'load-media' or"
    " set a duration with 'metadata set-media-length'."
)
HARMONY_NEEDS = f"harmony import needs: {rules.INSTALL_HARMONY}"
# A kept chord with a slash bass that TiLiA's `letter_symbol` can't draw.
_BASS_OUTSIDE = "{}: the bass isn't in the chord, so it is drawn in root position."
# A kept chord with a cell that isn't one, as for a color: the rules' reason, then this.
_DEFAULT_USED = "{}: the default is used."

_REQUIRED = ("harmony_or_key", "time", "symbol")  # in the order TiLiA looks for them
_KINDS = {"harmony": "harmony", "key": "mode"}
_OPTIONAL = {
    "harmony": ("comments", "display_mode", "custom_text", "custom_text_font_type"),
    "mode": ("comments",),
}
_DEFAULTS = {kind: COMPONENT_SHAPES[kind].defaults for kind in _OPTIONAL}
# A chord's columns that keep the row when they aren't one.
_OPTIONS = ("display_mode", "custom_text_font_type")
# How the rules' reasons about a time start: its bounds, and another at that time.
_TIME_REASON_STARTS = ("Time ", "There is already")

# tilia/timelines/harmony/constants.py's.
_NOTE_NAME_TO_INT = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
_INT_TO_NOTE_NAME = {v: k for k, v in _NOTE_NAME_TO_INT.items()}
_ROMAN_TO_INT = {"I": 0, "II": 1, "III": 2, "IV": 3, "V": 4, "VI": 5, "VII": 6}
_CHORD_COMMON_NAME_TO_TYPE = {
    "augmented seventh chord": "augmented-seventh",
    "half-diminished seventh chord": "half-diminished-seventh",
    "major seventh chord": "major-seventh",
    "augmented triad": "augmented",
    "diminished seventh chord": "diminished-seventh",
    "dominant seventh chord": "dominant-seventh",
    "diminished triad": "diminished",
    "minor seventh chord": "minor-seventh",
    "augmented major tetrachord": "augmented-major-13th",
    "major triad": "major",
    "minor triad": "minor",
}

_BASE_AND_TONE_TO_QUALITY = {
    base_and_tone: quality
    for quality, base_and_tone in rules.ADDED_TONE_QUALITIES.items()
}

_ALTERATION_TO_ACCIDENTAL = {-1: "b", 0: "", 1: "#"}

# A tone added after a Roman numeral's figures: "V7b9", "V65(b9)". A tone
# without an accidental needs "add" or parentheses, since "V9" is a ninth
# chord and "I6" an inversion.
_ROMAN_ADDED_TONE_PATTERNS = (
    re.compile(r"\((?:add)?([b#]?)(\d+)\)$"),
    re.compile(r"add([b#]?)(\d+)$"),
    re.compile(r"([b#])(9|11|13)$"),
)


@dataclass(frozen=True)
class _Row:
    """A row of the CSV whose kind and time can be read."""

    csv_row: CsvRow
    kind: str  # "harmony" or "mode"
    time: float
    symbol: str


def harmony_available() -> bool:
    """Whether music21 can be imported, which the `harmony` extra installs. It is
    looked for, not imported."""
    return importlib.util.find_spec("music21") is not None


def get_harmony_params_from_text(
    text: str, key: music21.key.Key | str | None
) -> tuple[bool, dict[str, Any] | None]:
    """A chord symbol's attributes: `step`, `accidental`, `inversion`, `quality` and
    `applied_to`.

    `text` is a letter symbol ("Bb7/D") or a Roman numeral ("V7/V"), read in `key`, a
    `music21.key.Key` or what music21 reads as one. Gives `(True, attributes)`, or
    `(False, None)` for a symbol it can't read, whatever music21 raises on it.

    Raises `ImportFailed` without the `harmony` extra.
    """
    _need_music21(None)
    try:
        return _get_harmony_params_from_text(text, key)
    except Exception as error:  # whatever music21 raises
        logger.debug("reading the chord symbol %r raised: %r", text, error)
        return False, None


def get_mode_params_from_text(text: str) -> tuple[bool, dict[str, Any] | None]:
    """A key symbol's attributes: `step`, `accidental` and `type`.

    `text` is a tonic, as music21 reads it, or with "b" for a flat: "Eb", "f#". Gives
    `(True, attributes)`, or `(False, None)` for a symbol it can't read, whatever
    music21 raises on it.

    Raises `ImportFailed` without the `harmony` extra.
    """
    _need_music21(None)
    try:
        return _get_mode_params_from_text(text)
    except Exception as error:  # whatever music21 raises
        logger.debug("reading the key symbol %r raised: %r", text, error)
        return False, None


def import_by_time(
    document: tla.Document, target: str, path: str | os.PathLike[str]
) -> ImportResult:
    """Replace the chords and keys of the harmony timeline `target` with a CSV's, in
    memory.

    `harmony_or_key`, `time` and `symbol` are required; `comments` is optional, and
    for a chord so are `display_mode`, `custom_text` and `custom_text_font_type`.
    Times are read in the document's time unit. A row that can't be read, with a symbol
    music21 can't read, or that the rules refuse, is skipped and reported. A chord kept
    whose slash bass isn't in the chord gets a note, since TiLiA draws it in root
    position, and one whose `display_mode` or `custom_text_font_type` isn't one gets the
    default, and a note.

    Raises `ImportFailed` when the import can't run, without the `harmony` extra too,
    and `OSError` for a file that can't be opened; both change nothing.
    """
    path = Path(path)
    _need_music21(path)
    if document.media_length is None:
        raise ImportFailed(path, _NO_MEDIA_LENGTH)
    header, csv_rows = read_csv(path)
    for column in _REQUIRED:
        if column not in header:
            raise ImportFailed(path, _COLUMN_NOT_FOUND.format(column))

    problems: list[RowProblem] = []
    rows = [
        row
        for csv_row in csv_rows
        if (row := _read_row(csv_row, path, problems)) is not None
    ]
    keys = _kept(document.media_length, _keys(rows, path, problems), path, problems)
    built = _build(rows, keys, path, problems)
    kept = _kept(document.media_length, built, path, problems)
    for csv_row, component in kept:
        problems.extend(_notes(path, csv_row, component))
    components = [component for _, component in kept]

    commit(document, target, components)
    # In the CSV's order, whichever step found each: reading, the keys, the chords.
    problems.sort(key=lambda problem: problem.line)
    return ImportResult(
        created=[component.id for component in components],
        rows=len(csv_rows),
        problems=problems,
    )


def _need_music21(path: Path | None) -> None:
    """Raises `ImportFailed` unless music21 can be imported: without the `harmony`
    extra it names the command that installs it, and for a music21 that is installed
    but won't import it gives the rules' text for that."""
    if not harmony_available():
        raise ImportFailed(path, HARMONY_NEEDS)
    try:
        import music21  # noqa: F401
    except Exception as error:  # as the rules' look-up: whatever the error is
        message = printable(str(rules.CantCheck("harmony", error)))
        raise ImportFailed(path, message) from error


def _read_row(csv_row: CsvRow, path: Path, problems: list[RowProblem]) -> _Row | None:
    """A row's kind, time and symbol, or None when its kind or its time can't be read:
    the first cell of them that can't. A symbol is read later, with the keys."""
    values = csv_row.values
    cell = values.get("harmony_or_key", "")
    kind = _KINDS.get(cell)
    if kind is None:
        message = rules.not_valid("harmony_or_key", cell)
        problems.append(_problem(path, csv_row, "harmony_or_key", message))
        return None
    cell = values.get("time", "")
    try:
        time = float(cell)
    except ValueError:
        problems.append(_problem(path, csv_row, "time", rules.not_valid("time", cell)))
        return None
    return _Row(csv_row, kind, time, values.get("symbol", ""))


def _keys(
    rows: Sequence[_Row], path: Path, problems: list[RowProblem]
) -> list[tuple[CsvRow, tla.Component]]:
    """The keys of `rows`, in their order, but those whose symbol can't be read."""
    built: list[tuple[CsvRow, tla.Component]] = []
    for row in rows:
        if row.kind == "mode":
            success, params = get_mode_params_from_text(row.symbol)
            if success:
                built.append((row.csv_row, _component(row, params)))
            else:
                problems.append(_not_a_symbol(path, row))
    return built


def _kept(
    media_length: float,
    built: Sequence[tuple[CsvRow, tla.Component]],
    path: Path,
    problems: list[RowProblem],
) -> list[tuple[CsvRow, tla.Component]]:
    """Those of `built` that the rules keep, in their order; the others are reported.

    Raises `ImportFailed` when a rule couldn't be checked, so that nothing goes in
    unchecked.
    """
    checked = rules.check_timeline(
        media_length, [component for _, component in built], skip_broken=True
    )
    kept: list[tuple[CsvRow, tla.Component]] = []
    for csv_row, component in built:
        found = checked[component.id]
        if found.cant_check is not None:
            raise ImportFailed(path, printable(str(found.cant_check)))
        if found.outcome:
            kept.append((csv_row, component))
        else:
            reason = found.outcome.reason
            column = _column_of(reason, component.attrs)
            problems.append(_problem(path, csv_row, column, reason))
    return kept


def _build(
    rows: Sequence[_Row],
    keys: Sequence[tuple[CsvRow, tla.Component]],
    path: Path,
    problems: list[RowProblem],
) -> list[tuple[CsvRow, tla.Component]]:
    """The components of `rows`, in their order, as TiLiA creates them one row after
    the other: a chord is read in the key in force among `keys`, the keys kept, of the
    rows before it, and a key updates the chords of the rows before it. A chord the
    rules then refuse changes nothing, since nothing reads a chord's values but itself.
    """
    key_of_line = {csv_row.line: key for csv_row, key in keys}
    built: list[tuple[CsvRow, tla.Component]] = []
    chords: list[tla.Component] = []
    in_force = _KeysInForce()
    for row in rows:
        if row.kind == "mode":
            key = key_of_line.get(row.csv_row.line)
            if key is not None:
                _update_applied_to(chords, key, in_force)
                in_force.add(key)
                built.append((row.csv_row, key))
            continue
        success, params = get_harmony_params_from_text(
            row.symbol, in_force.at(row.time)
        )
        # music21 reads some symbols with no chord type, such as "C5". The reading
        # gives them, as TiLiA's does, and the cell's symbol is what can't be used.
        if success and params["quality"]:
            component = _component(row, params)
            chords.append(component)
            built.append((row.csv_row, component))
        else:
            problems.append(_not_a_symbol(path, row))
    return built


def _component(row: _Row, params: Mapping[str, Any] | None) -> tla.Component:
    values = row.csv_row.values
    bad_options = _bad_options(row.csv_row) if row.kind == "harmony" else {}
    return tla.Component(
        id=tla.new_id(),
        kind=row.kind,
        attrs={
            **_DEFAULTS[row.kind],
            **{
                name: values[name]
                for name in _OPTIONAL[row.kind]
                if values.get(name) and name not in bad_options
            },
            **(params or {}),
            "time": row.time,
        },
    )


def _bad_options(csv_row: CsvRow) -> dict[str, str]:
    """The reasons for a chord's cells that the rules say aren't one, by column."""
    reasons = {}
    for column in _OPTIONS:
        cell = csv_row.values.get(column)
        if cell and not (outcome := rules.harmony_option(column, cell)):
            reasons[column] = outcome.reason
    return reasons


def _column_of(reason: str, attrs: Mapping[str, Any]) -> str:
    """The column a rule's reason about `attrs` is about: the rest of a chord's or a
    key's values are what its symbol reads as, and its options have been checked."""
    if reason.startswith(_TIME_REASON_STARTS) or reason == rules.not_valid(
        "time", attrs["time"]
    ):
        return "time"
    return "symbol"


def _notes(path: Path, csv_row: CsvRow, component: tla.Component) -> list[RowProblem]:
    """What a row that is kept is told about its component: a key has nothing to be
    told, as those cells aren't read on its row."""
    if component.kind != "harmony":
        return []
    notes = []
    attrs = component.attrs
    if not _bass_is_in_the_chord(attrs["quality"], attrs["inversion"]):
        message = _BASS_OUTSIDE.format(printable(csv_row.values["symbol"]))
        notes.append(_problem(path, csv_row, "symbol", message, skipped=False))
    for column, reason in _bad_options(csv_row).items():
        message = _DEFAULT_USED.format(reason.removesuffix("."))
        notes.append(_problem(path, csv_row, column, message, skipped=False))
    return notes


def _bass_is_in_the_chord(quality: str, inversion: int) -> bool:
    """Whether TiLiA's `letter_symbol` draws a chord in its inversion: it builds
    `ChordSymbol(note, inversion=inversion)`, from the base quality, and falls back to
    root position when music21 raises `ChordException`.

    music21 looks for a tone of the chord at that position in a stack of thirds, by
    its letter: 1 is the third, 4 the ninth, so the second. `CHORD_TYPES` lists a
    chord type's tones by degree ("1,-3,5"), so no chord has to be built here.
    """
    import music21

    base, _ = rules.split_added_tone(quality)
    position = 2 * inversion % 7
    degrees = str(music21.harmony.CHORD_TYPES[base][0]).split(",")
    return any((int(degree.lstrip("#-")) - 1) % 7 == position for degree in degrees)


def _not_a_symbol(path: Path, row: _Row) -> RowProblem:
    message = rules.not_valid("symbol", row.symbol)
    return _problem(path, row.csv_row, "symbol", message)


def _problem(
    path: Path, csv_row: CsvRow, column: str, message: str, *, skipped: bool = True
) -> RowProblem:
    return RowProblem(
        path=path, line=csv_row.line, column=column, message=message, skipped=skipped
    )


class _KeysInForce:
    """The keys so far, in the order of their times, which the rules make different:
    what TiLiA's `HarmonyTimeline` and its component manager find among its modes."""

    def __init__(self) -> None:
        self._times: list[float] = []
        self._steps: list[int] = []
        self._keys: list[music21.key.Key] = []

    def add(self, mode: tla.Component) -> None:
        attrs = mode.attrs
        place = bisect.bisect_right(self._times, attrs["time"])
        self._times.insert(place, attrs["time"])
        self._steps.insert(place, attrs["step"])
        self._keys.insert(place, _key_of(attrs))

    def at(self, time: float) -> music21.key.Key:
        """`get_key_by_time`: the last key at or before `time`, else C major."""
        place = bisect.bisect_right(self._times, time)
        if not place:
            import music21

            return music21.key.Key("CM")
        return self._keys[place - 1]

    def next_time(self, time: float) -> float:
        """`_get_next_mode_time`: the first key's time after `time`, else infinity."""
        place = bisect.bisect_right(self._times, time)
        return self._times[place] if place < len(self._times) else math.inf

    def previous_step(self, time: float) -> int:
        """`_get_previous_mode`'s step: the last key's before `time`, else C's."""
        place = bisect.bisect_left(self._times, time)
        return self._steps[place - 1] if place else 0


def _key_of(attrs: Mapping[str, Any]) -> music21.key.Key:
    """TiLiA's `Mode.key`."""
    import music21

    tonic = (
        _INT_TO_NOTE_NAME[attrs["step"]]
        + music21.pitch.Accidental(attrs["accidental"]).modifier
    )
    return music21.key.Key(tonic, mode=attrs["type"])


def _update_applied_to(
    chords: Collection[tla.Component], mode: tla.Component, in_force: _KeysInForce
) -> None:
    """TiLiA's `_update_harmony_applied_to_on_mode_creation`, for the chords from the
    new key's time up to the next key's, that time included: each `applied_to` is
    counted from the new key instead of the one before it. `set_data` refuses a step
    that doesn't exist, and that chord keeps the value it has."""
    time = mode.attrs["time"]
    next_time = in_force.next_time(time)
    previous_step = in_force.previous_step(time)
    for chord in chords:
        if next_time >= chord.attrs["time"] >= time:
            applied_to = chord.attrs["applied_to"] + previous_step - mode.attrs["step"]
            if 0 <= applied_to <= 6:
                chord.attrs["applied_to"] = applied_to


# TiLiA's reading of a chord symbol: tilia/timelines/harmony/components/harmony.py.


def _get_harmony_params_from_text(
    text: str, key: music21.key.Key | str | None
) -> tuple[bool, dict[str, Any] | None]:
    music21_object, object_type, added_tone = _get_harmony_music21_object_from_text(
        text, key
    )
    if not object_type:
        return False, None

    params = _get_harmony_params_from_music21_object(
        music21_object, object_type, added_tone
    )
    if added_tone and params["inversion"] > rules.get_inversion_amount(
        params["quality"]
    ):
        # The added tone is in the bass, as in "C7b9/Db". No inversion puts it
        # there.
        return False, None
    return True, params


def _replace_special_abbreviations(text: str) -> str:
    # these don't get correctly parsed by music21
    sub_args = [("dimb9", "ob9"), ("9#5", "+9"), ("m7b5", "ø7"), ("m#7", "minmaj7")]
    for pattern, replacement in sub_args:
        text = re.sub(pattern, replacement, text)

    return text


def _get_harmony_music21_object_from_text(
    text: str, key: music21.key.Key | str | None
) -> (
    tuple[music21.harmony.ChordSymbol | music21.roman.RomanNumeral, str, str]
    | tuple[None, None, str]
):
    """
    Return the music21 object for the text, its kind, and the tone the text
    adds to the object's quality, or "" if they are no added-tone quality.
    """
    import music21

    # "Cad64" is the key's cadential six-four, as "V(64)" is.
    text = re.sub(r"^[Cc]ad64(?=/|$)", "V(64)", text)
    text, prefixed_accidental = _extract_prefixed_accidental(text)
    text = _format_harmony_postfix_accidental(text)
    text = _replace_special_abbreviations(text)
    if text.startswith(tuple(_NOTE_NAME_TO_INT)) and not prefixed_accidental:
        spelled = _spell_added_tone(text)
        try:
            symbol = music21.harmony.ChordSymbol(spelled)
            added_tone = _get_added_tone(symbol)
            # music21 reads no parentheses, so a text that needed respelling
            # is read only as an added-tone quality: "C7(b9)" is read, while
            # "Cm7(b9)" is refused, as before.
            if added_tone or spelled == text:
                return symbol, "letter", added_tone
        # I don't know exactly what exceptions music21 can throw.
        except Exception:
            pass
    elif text.startswith(("I", "i", "V", "v")):
        # music21 reads a tone after a Roman numeral's figures as another
        # figure, so the numeral is read without it.
        text, added_tone = _split_roman_added_tone(text)
        try:
            roman_numeral = music21.roman.RomanNumeral(prefixed_accidental + text, key)
            quality = _CHORD_COMMON_NAME_TO_TYPE[roman_numeral.commonName]
            if added_tone and (quality, added_tone) not in _BASE_AND_TONE_TO_QUALITY:
                raise KeyError(added_tone)
            return roman_numeral, "roman", added_tone
        except (ValueError, KeyError):
            pass

    return None, None, ""


def _spell_added_tone(text: str) -> str:
    """
    Spell an added tone as music21 reads it: "C7(b9)" as "C7b9", and "C(9)",
    "C(add9)" and "C6/9" with "add", as "Cadd9" and "C6add9".
    """
    text = text.replace("6/9", "6add9")
    return re.sub(
        r"\((?:add)?([b#]?)(\d+)\)", lambda match: (match[1] or "add") + match[2], text
    )


def _get_added_tone(symbol: music21.harmony.ChordSymbol) -> str:
    """
    Return the tone the chord symbol adds to its chord type, as "b9", if
    together they are an added-tone quality. Otherwise return "", and the
    chord symbol is read as its chord type, as before.
    """
    modifications = symbol.chordStepModifications
    if len(modifications) != 1 or modifications[0].modType != "add":
        return ""
    modification = modifications[0]
    alteration = modification.interval.semitones if modification.interval else 0
    accidental = _ALTERATION_TO_ACCIDENTAL.get(alteration)
    if accidental is None:
        return ""
    tone = accidental + str(modification.degree)
    return tone if (symbol.chordKind, tone) in _BASE_AND_TONE_TO_QUALITY else ""


def _split_roman_added_tone(text: str) -> tuple[str, str]:
    """Split "V7b9/IV" into "V7/IV" and "b9". The tone is "" if there is none."""
    numeral, slash, applied_to = text.partition("/")
    for pattern in _ROMAN_ADDED_TONE_PATTERNS:
        if match := pattern.search(numeral):
            accidental, degree = match.groups()
            numeral = numeral[: match.start()]
            if accidental and not numeral[-1:].isdigit():
                # An altered tone is added to a seventh chord: "Vb9" is "V7b9".
                numeral += "7"
            return numeral + slash + applied_to, accidental + degree
    return text, ""


def _get_harmony_params_from_music21_object(
    obj: music21.harmony.ChordSymbol | music21.roman.RomanNumeral,
    kind: str,
    added_tone: str = "",
) -> dict[str, Any]:
    step = _NOTE_NAME_TO_INT[obj.root().step]
    accidental = int(obj.root().alter)
    inversion = obj.inversion() if obj.inversion() else 0
    if kind == "roman":
        quality = _CHORD_COMMON_NAME_TO_TYPE[obj.commonName]
        applied_to = (
            _ROMAN_TO_INT[obj.secondaryRomanNumeral.figure.upper()]
            if obj.secondaryRomanNumeral
            else 0
        )
    else:
        quality = obj.chordKind
        applied_to = 0
    if added_tone:
        quality = _BASE_AND_TONE_TO_QUALITY[quality, added_tone]

    return {
        "step": step,
        "accidental": accidental,
        "inversion": inversion,
        "quality": quality,
        "applied_to": applied_to,
    }


def _format_harmony_postfix_accidental(text: str) -> str:
    text = re.sub("([A-G][b#]*)-", "\\1m", text)
    text = re.sub("([A-G])bb", "\\1--", text)
    text = re.sub("([A-G])b", "\\1-", text)
    return text


def _extract_prefixed_accidental(text: str) -> tuple[str, str]:
    if not text:
        return "", ""

    accidental = ""

    while text and text[0] in ["-", "#", "b"]:
        accidental += text[0]
        text = text[1:]

    return text, accidental


# TiLiA's reading of a key symbol: tilia/timelines/harmony/components/mode.py.


def _get_mode_params_from_text(text: str) -> tuple[bool, dict[str, Any] | None]:
    success, music21_object = _get_mode_music21_object_from_text(text)
    if not success:
        return False, None

    return True, _get_mode_params_from_music21_object(music21_object)


def _format_mode_postfix_accidental(text: str) -> str:
    if len(text) > 1 and text[1] == "b":
        text = text[0] + "-" + text[2:]
        if len(text) > 2 and text[2] == "b":
            text = text[:2] + "-" + text[3:]
    return text


def _get_mode_music21_object_from_text(
    text: str,
) -> tuple[bool, music21.key.Key | None]:
    import music21

    text = _format_mode_postfix_accidental(text)

    valid_initial_chars = list(_NOTE_NAME_TO_INT) + list(
        map(str.lower, _NOTE_NAME_TO_INT)
    )
    if text.startswith(tuple(valid_initial_chars)):
        try:
            return True, music21.key.Key(text)
        except (ValueError, music21.Music21Exception):
            return False, None

    return False, None


def _get_mode_params_from_music21_object(obj: music21.key.Key) -> dict[str, Any]:
    return {
        "step": _NOTE_NAME_TO_INT[obj.tonic.step],
        "accidental": int(obj.tonic.alter),
        "type": obj.mode,
    }
