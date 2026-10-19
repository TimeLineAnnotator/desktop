"""The one set of rules for a valid component.

Everything that creates or changes a component goes through these rules and
keeps none of its own: the importers, the `tilia` command, bulk edits, and the
reader and the writer of `.tla` files. TiLiA checks a component in several
places (when it creates one, when it sets a value, in its editing operations),
which don't always agree; the rules are the strictest of them and of the
format's schema.

There is one function per kind the importers create. Each takes the media
length, the timeline's other components (not the one checked) and the
attributes of the component to check, and gives the first rule they break:
`(False, reason)`, or `(True, "")` when they break none. The reasons are
TiLiA's, word for word, where TiLiA has one. A value that isn't one always
reads `<value> is not a valid <attribute>.`, whatever the kind.

A harmony's quality and inversion and a mode's type are checked against the
installed music21, as TiLiA checks them, so checking a harmony or a mode needs
the `harmony` extra. Without it, the other rules are checked, and when none is
broken, `CantCheck` is raised, before the color is checked: a bad color mustn't
hide that a rule couldn't be checked. music21 is imported only when a harmony or
a mode is checked.
"""

from __future__ import annotations

import importlib.util
import math
import string
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from types import ModuleType
from typing import TYPE_CHECKING, Any

import webcolors

if TYPE_CHECKING:
    from tilia_core import tla

INSTALL_HARMONY = 'pip install "tilia-core[harmony]"'

# TiLiA's values (tilia/timelines/harmony/constants.py). Qualities and mode types
# are music21's.
HARMONY_ACCIDENTALS = (2, 1, 0, -1, -2)
HARMONY_DISPLAY_MODES = ("letter", "roman", "custom")
FONT_TYPES = ("analytic", "normal")
_STEPS = range(7)
_LEVELS = (1, 2)
_NOT_MODE_TYPES = ("ionian", "aeolian")
# Qualities music21 has no chord type for, each a chord type it has plus one added
# tone, spelled as in a chord symbol, from the root: TiLiA's, as `dev` has them
# since 43a61224 and 28539120. TiLiA takes them from here once it checks with
# the rules.
ADDED_TONE_QUALITIES: dict[str, tuple[str, str]] = {
    "dominant-seventh-flat-ninth": ("dominant-seventh", "b9"),
    "dominant-seventh-sharp-ninth": ("dominant-seventh", "#9"),
    "dominant-seventh-sharp-eleventh": ("dominant-seventh", "#11"),
    "dominant-seventh-flat-thirteenth": ("dominant-seventh", "b13"),
    "dominant-seventh-added-thirteenth": ("dominant-seventh", "13"),
    "dominant-ninth-sharp-eleventh": ("dominant-ninth", "#11"),
    "major-seventh-sharp-eleventh": ("major-seventh", "#11"),
    "major-seventh-added-sixth": ("major-seventh", "6"),
    "major-sixth-added-ninth": ("major-sixth", "9"),
    "minor-sixth-added-ninth": ("minor-sixth", "9"),
    "major-added-ninth": ("major", "9"),
    "minor-added-ninth": ("minor", "9"),
    "minor-seventh-added-eleventh": ("minor-seventh", "11"),
}
# Qualities TiLiA keeps in root position, whatever their intervals.
_NO_INVERSION_QUALITIES = frozenset(
    {"Italian", "French", "German", "Neapolitan", "Tristan", "power"}
)

# Hierarchy boundaries less than this far apart count as the same, as TiLiA's
# `get_boundary_conflicts` compares them since `dev`'s 2ceec157: files TiLiA saved
# before then hold boundaries a few ulps apart where they should meet.
_TIME_ABS_TOL = 1e-9

# The names TiLiA's reasons give the point kinds (their `frontend_name`).
_POINT_NAMES = {
    "marker": "marker",
    "harmony": "harmony",
    "mode": "mode",
    "beat": "beat",
    "pdf_marker": "PDF page marker",
}

_TEXTS = ("label", "comments", "custom_text")
_SEGMENT_TIMES = ("start", "end", "pre_start", "post_end")
_UNSET_TIMES = ("pre_start", "post_end")  # None: they follow the start and the end

# A range row's id, as TiLiA's `generate_row_id` makes it.
ROW_ID_LENGTH = 6
ROW_ID_CHARACTERS = string.ascii_letters + string.digits

# The colors Qt reads: #RGB, #RRGGBB, #AARRGGBB, #RRRGGGBBB and #RRRRGGGGBBBB,
# and the names in `QColor.colorNames()`, which are CSS 3's (SVG 1.0's) and
# "transparent". CSS 3's come from webcolors, so the core keeps no copy of them.
_HEX_LENGTHS = (3, 6, 8, 9, 12)
_HEX_DIGITS = frozenset(string.hexdigits)
_COLOR_NAMES = frozenset(webcolors.names("css3")) | {"transparent"}


class Outcome(tuple[bool, str]):
    """What checking the rules gives: `(True, "")`, or `(False, reason)`.

    It is true when no rule is broken, so `if rules.marker(...):` reads as "the
    marker keeps to the rules"; it also unpacks as `ok, reason`. `others` are
    the ids of the other components a broken rule is about: those at the same
    time or place, the hierarchies it crosses, the ranges it should join.
    """

    others: tuple[str, ...]

    def __new__(cls, ok: bool, reason: str = "", others: Iterable[str] = ()) -> Outcome:
        outcome = super().__new__(cls, (bool(ok), reason))
        outcome.others = tuple(others)
        return outcome

    def __bool__(self) -> bool:
        return self[0]

    def __getnewargs__(self) -> tuple[bool, str, tuple[str, ...]]:  # type: ignore[override]
        # What copy and pickle give __new__: a tuple's would be the pair alone.
        return self[0], self[1], self.others

    @property
    def ok(self) -> bool:
        return self[0]

    @property
    def reason(self) -> str:
        return self[1]


OK = Outcome(True)


class CantCheck(Exception):
    """The rules that need music21 can't be checked: the `harmony` extra is missing,
    or music21 won't import (the error is the exception's cause).

    This isn't a broken rule: the component may well keep to them.
    """

    command = INSTALL_HARMONY

    def __init__(self, kind: str, error: Exception | None = None) -> None:
        if error is None:
            message = f"checking a {kind} needs: {INSTALL_HARMONY}"
        else:
            message = (
                f"checking a {kind} needs music21, which can't be imported"
                f" ({type(error).__name__}: {error}): {INSTALL_HARMONY}"
            )
        super().__init__(message)
        self.kind = kind
        self.error = error

    def __reduce__(self) -> tuple[Any, ...]:
        # The error isn't carried, since it may not copy or pickle: its text is in
        # the message, which is.
        return type(self), (self.kind,), {"args": self.args, "error": None}


# The private functions give the first rule they find broken, or None. `_kept`
# checks them in order, each only once the ones before it are kept. Then it raises
# `CantCheck` when the rules that need music21 couldn't be checked, and only then
# checks the color: an importer keeps a row whose color isn't one, with the
# default color, so a bad color mustn't hide another broken rule, nor that a rule
# couldn't be checked.

Check = Callable[[], "Outcome | None"]


def _kept(
    attrs: Mapping[str, Any],
    *checks: Check,
    cant_check: CantCheck | None = None,
) -> Outcome:
    """The first rule `checks` find broken, else `cant_check` raised, when the
    rules that need music21 couldn't be checked, else the color's outcome."""
    for check in checks:
        broken = check()
        if broken is not None and not broken:
            return broken
    if cant_check is not None:
        raise cant_check from cant_check.error
    broken = _color_of(attrs)
    return OK if broken is None else broken


def marker(
    media_length: float, others: Iterable[tla.Component], attrs: Mapping[str, Any]
) -> Outcome:
    """A marker."""
    return _kept(attrs, lambda: _point("marker", media_length, others, attrs))


def beat(
    media_length: float, others: Iterable[tla.Component], attrs: Mapping[str, Any]
) -> Outcome:
    """A beat. Its measure mark and beat unit follow the measure table's rules."""
    return _kept(attrs, lambda: _point("beat", media_length, others, attrs))


def pdf_marker(
    media_length: float,
    others: Iterable[tla.Component],
    attrs: Mapping[str, Any],
    *,
    page_count: int,
) -> Outcome:
    """A PDF marker, in a PDF of `page_count` pages: 0 for a PDF that can't be read."""
    return _kept(
        attrs,
        lambda: _point("pdf_marker", media_length, others, attrs),
        lambda: _page(attrs.get("page_number"), page_count),
    )


def harmony(
    media_length: float, others: Iterable[tla.Component], attrs: Mapping[str, Any]
) -> Outcome:
    """A harmony. Without music21, raises `CantCheck` when no rule but the color is
    broken: the color is checked after it."""
    music21, error = _music21()
    return _kept(
        attrs,
        lambda: _point("harmony", media_length, others, attrs),
        lambda: _one_of(attrs, "step", _STEPS),
        lambda: _one_of(attrs, "applied_to", _STEPS),
        lambda: _one_of(attrs, "accidental", HARMONY_ACCIDENTALS),
        lambda: _quality_and_inversion(music21, attrs) if music21 else None,
        lambda: _one_of(attrs, "level", _LEVELS),
        lambda: _one_of(attrs, "display_mode", HARMONY_DISPLAY_MODES),
        lambda: _one_of(attrs, "custom_text_font_type", FONT_TYPES),
        cant_check=None if music21 else CantCheck("harmony", error),
    )


def mode(
    media_length: float, others: Iterable[tla.Component], attrs: Mapping[str, Any]
) -> Outcome:
    """A key. Without music21, raises `CantCheck` when no rule but the color is
    broken: the color is checked after it."""
    music21, error = _music21()
    return _kept(
        attrs,
        lambda: _point("mode", media_length, others, attrs),
        lambda: _one_of(attrs, "step", _STEPS),
        lambda: _one_of(attrs, "accidental", HARMONY_ACCIDENTALS),
        lambda: _mode_type(music21, attrs) if music21 else None,
        lambda: _one_of(attrs, "level", _LEVELS),
        cant_check=None if music21 else CantCheck("mode", error),
    )


def hierarchy(
    media_length: float, others: Iterable[tla.Component], attrs: Mapping[str, Any]
) -> Outcome:
    """A hierarchy. Hierarchies nest: one that overlaps another lies inside it,
    at a lower level."""
    start, end, level = attrs.get("start"), attrs.get("end"), attrs.get("level")
    hierarchies = [other for other in others if other.kind == "hierarchy"]
    return _kept(
        attrs,
        lambda: _every_kind(attrs, _SEGMENT_TIMES),
        lambda: _hierarchy_times(start, end, media_length),
        lambda: _hierarchy_level(level),
        lambda: _pre_start(attrs.get("pre_start"), start),
        lambda: _post_end(attrs.get("post_end"), end, media_length),
        lambda: _same_place(start, end, level, hierarchies),
        lambda: _crossed(start, end, level, hierarchies),
    )


def range_(
    media_length: float,
    others: Iterable[tla.Component],
    attrs: Mapping[str, Any],
    *,
    rows: Sequence[Mapping[str, Any]],
) -> Outcome:
    """A range, in a timeline whose attribute `rows` is `rows`.

    Ranges in a row may overlap.
    """
    start, end = attrs.get("start"), attrs.get("end")
    row_ids = [row.get("id") for row in rows]
    return _kept(
        attrs,
        lambda: _every_kind(attrs, _SEGMENT_TIMES),
        lambda: _range_place(attrs.get("row_id"), row_ids, start, end, media_length),
        lambda: _pre_start(attrs.get("pre_start"), start),
        lambda: _post_end(attrs.get("post_end"), end, media_length),
        lambda: _joined(attrs, others, rows),
    )


def range_rows(rows: Sequence[Mapping[str, Any]]) -> Outcome:
    """A range timeline's rows: each with its own id of six letters and digits,
    a name, and a color or none."""
    ids: set[str] = set()
    for row in rows:
        row_id = row.get("id")
        if not _is_row_id(row_id):
            return _broken(not_valid("row_id", row_id))
        if row_id in ids:
            return _broken(f"There is already a row with the id {row_id}.")
        ids.add(row_id)
        name = row.get("name")
        if not isinstance(name, str):
            return _broken(not_valid("row_name", name))
    for row in rows:
        broken = _color_of(row)
        if broken is not None:
            return broken
    return OK


def color(value: Any) -> Outcome:
    """A color: the default (None or ""), or one Qt reads, checked without Qt.

    An importer keeps a row whose color isn't one, with the kind's default color
    instead, and a note.
    """
    if value is None or value == "":
        return OK
    if isinstance(value, str) and _qt_reads(value):
        return OK
    return _broken(not_valid("color", value))


def split_added_tone(quality: str) -> tuple[str, str]:
    """A quality's base quality and added tone, or the quality and ""."""
    return ADDED_TONE_QUALITIES.get(quality, (quality, ""))


def not_valid(attribute: str, value: Any) -> str:
    """The reason for a value of `attribute` that isn't one, for every kind.

    The rules give it for a value they refuse as not being one, such as a time of
    nan, and the importers for a value they can't read, so the two read alike.
    """
    return f"{_shown(value)} is not a valid {attribute.replace('_', ' ')}."


def _point(
    kind: str,
    media_length: float,
    others: Iterable[tla.Component],
    attrs: Mapping[str, Any],
) -> Outcome | None:
    """The rules for every kind, the time's bounds, and no other at the same time."""
    broken = _every_kind(attrs, ("time",))
    if broken is not None:
        return broken
    time = attrs["time"]
    if time < 0:
        return _broken(f"Time can't be negative. Got '{_media_time(time)}'")
    if time > media_length:
        return _broken(
            f"Time '{_media_time(time)}' is bigger than media time"
            f" '{_media_time(media_length)}'"
        )
    same = [
        other.id
        for other in others
        if other.kind == kind and other.attrs.get("time") == time
    ]
    if same:
        return Outcome(
            False,
            f"There is already a {_POINT_NAMES[kind]} component at the selected position.",
            same,
        )
    return None


def _every_kind(attrs: Mapping[str, Any], times: Iterable[str]) -> Outcome | None:
    """Times are finite numbers and texts are text. The color is checked last."""
    for name in times:
        value = attrs.get(name)
        if value is None and name in _UNSET_TIMES:
            continue
        if not _is_number(value):
            return _broken(not_valid(name, value))
    for name in _TEXTS:
        if name in attrs and not isinstance(attrs[name], str):
            return _broken(not_valid(name, attrs[name]))
    return None


def _color_of(attrs: Mapping[str, Any]) -> Outcome | None:
    if "color" in attrs:
        outcome = color(attrs["color"])
        if not outcome:
            return outcome
    return None


def _page(page_number: Any, page_count: int) -> Outcome | None:
    if not _is_integer(page_number):
        return _broken(not_valid("page_number", page_number))
    if not 1 <= page_number <= page_count:
        return _broken("The PDF has no page with that number.")
    return None


def _one_of(
    attrs: Mapping[str, Any], name: str, allowed: Collection[int | str]
) -> Outcome | None:
    """`name`, when the component has it, is one of `allowed`, as it is: 1.0 isn't 1."""
    if name not in attrs:
        return None
    value = attrs[name]
    if (_is_integer(value) or isinstance(value, str)) and value in allowed:
        return None
    return _broken(not_valid(name, value))


def _music21() -> tuple[ModuleType | None, Exception | None]:
    """music21, with what the rules read of it; or None, without the `harmony`
    extra, and with the error when music21 is installed but won't import,
    whatever the error is."""
    try:
        if importlib.util.find_spec("music21") is None:
            return None, None
        import music21.harmony
        import music21.key
    except Exception as error:
        return None, error
    return music21, None


def _quality_and_inversion(
    music21: ModuleType, attrs: Mapping[str, Any]
) -> Outcome | None:
    """The quality is one of music21's `CHORD_TYPES` or of TiLiA's added-tone
    qualities, and the inversion one it has."""
    quality = attrs.get("quality", "major")
    if not (
        isinstance(quality, str)
        and split_added_tone(quality)[0] in music21.harmony.CHORD_TYPES
    ):
        return _broken(not_valid("quality", quality))
    inversion = attrs.get("inversion", 0)
    if not (_is_integer(inversion) and 0 <= inversion <= _inversions(music21, quality)):
        return _broken(not_valid("inversion", inversion))
    return None


def _inversions(music21: ModuleType, quality: str) -> int:
    """A quality's inversions, as TiLiA's `get_inversion_amount` counts them: an
    added tone isn't one the chord can be inverted to."""
    quality, _ = split_added_tone(quality)
    if quality in _NO_INVERSION_QUALITIES:
        return 0
    intervals = str(music21.harmony.CHORD_TYPES[quality][0])
    return len(intervals.split(",")) - 1


def _mode_type(music21: ModuleType, attrs: Mapping[str, Any]) -> Outcome | None:
    """The type is one of music21's `modeSharpsAlter`, but ionian and aeolian."""
    types = [
        name for name in music21.key.modeSharpsAlter if name not in _NOT_MODE_TYPES
    ]
    return _one_of(attrs, "type", types)


def _hierarchy_times(start: float, end: float, media_length: float) -> Outcome | None:
    # TiLiA shows these as floats, whatever they were given as.
    start, end, media_length = float(start), float(end), float(media_length)
    if start > media_length:
        return _broken(
            f"Start time '{start}' is bigger than media time '{media_length}'"
        )
    if end > media_length:
        return _broken(f"End time '{end}' is bigger than media time '{media_length}'")
    if start < 0:
        return _broken(f"Start time can't be negative. Got '{start}'")
    if end <= start:
        return _broken(f"End time '{end}' should be bigger than start time '{start}'")
    return None


def _hierarchy_level(level: Any) -> Outcome | None:
    if not _is_integer(level):
        return _broken(not_valid("level", level))
    if level < 1:
        return _broken(f"Level can't be below 1. Got '{_shown(level)}'")
    return None


def _pre_start(pre_start: float | None, start: float) -> Outcome | None:
    """`pre_start`, when set, is from 0 to the start."""
    if pre_start is None:
        return None
    if pre_start < 0:
        return _broken("pre_start is outside media bounds.")
    if pre_start > start:
        return _broken("pre_start can't be after start time.")
    return None


def _post_end(
    post_end: float | None, end: float, media_length: float
) -> Outcome | None:
    """`post_end`, when set, is from the end to the media length."""
    if post_end is None:
        return None
    if post_end > media_length:
        return _broken("post_end is outside media bounds.")
    if post_end < end:
        return _broken("post_end can't be before end time.")
    return None


def _same_place(
    start: float, end: float, level: int, hierarchies: Iterable[tla.Component]
) -> Outcome | None:
    same = [
        other.id
        for other in hierarchies
        if (other.attrs.get("start"), other.attrs.get("end"), other.attrs.get("level"))
        == (start, end, level)
    ]
    if same:
        return Outcome(
            False,
            "There is already a hierarchy component at the selected position.",
            same,
        )
    return None


def _crossed(
    start: float, end: float, level: int, hierarchies: Iterable[tla.Component]
) -> Outcome | None:
    crossed = [
        other.id for other in hierarchies if _cross(start, end, level, other.attrs)
    ]
    if crossed:
        return Outcome(
            False, "Component would overlap with existing component.", crossed
        )
    return None


def _cross(start: float, end: float, level: int, other: Mapping[str, Any]) -> bool:
    """Whether two hierarchies overlap, and neither lies inside the other, lower.

    This is when TiLiA's `get_boundary_conflicts` finds a conflict between them, as
    `dev` has it since 2ceec157: times less than 1e-9 apart count as the same.
    """
    other_start, other_end = other.get("start"), other.get("end")
    other_level = other.get("level")
    if not (
        _is_comparable(other_start)
        and _is_comparable(other_end)
        and _is_comparable(other_level)
    ):
        return False
    if not (_lt(start, other_end) and _lt(other_start, end)):
        return False
    inside = _le(other_start, start) and _le(end, other_end) and level < other_level
    around = _le(start, other_start) and _le(other_end, end) and other_level < level
    return not (inside or around)


def _times_close(a: float, b: float) -> bool:
    """Whether two times count as the same, as TiLiA's `_times_close` says."""
    try:
        return math.isclose(a, b, abs_tol=_TIME_ABS_TOL)
    except OverflowError:  # an integer too large for a float is close only to itself
        return a == b


def _le(a: float, b: float) -> bool:
    return a < b or _times_close(a, b)


def _lt(a: float, b: float) -> bool:
    return a < b and not _times_close(a, b)


def _range_place(
    row_id: Any, row_ids: Sequence[Any], start: float, end: float, media_length: float
) -> Outcome | None:
    if not row_id or row_id not in row_ids:
        return _broken("Invalid row ID.")
    if start >= end:
        return _broken("Start time must be before end time.")
    if start < 0 or end > media_length:
        return _broken("Range is outside media bounds.")
    return None


def _joined(
    attrs: Mapping[str, Any],
    others: Iterable[tla.Component],
    rows: Sequence[Mapping[str, Any]],
) -> Outcome | None:
    """`joined_right`, when set, is a next range in the row, starting at this one's end.

    The next ranges are those of the row that start first after this one starts.
    The reasons are the range importer's (`_apply_pending_joins`).
    """
    joined = attrs.get("joined_right")
    if joined is None:
        return None
    row_id, start, end = attrs["row_id"], attrs["start"], attrs["end"]
    row = next((row.get("name") for row in rows if row.get("id") == row_id), row_id)
    later = [
        other
        for other in others
        if other.kind == "range"
        and other.attrs.get("row_id") == row_id
        and _is_number(other.attrs.get("start"))
        and other.attrs["start"] > start
    ]
    if not later:
        return _broken(
            f"joined_with_next=true on last range of row {row!r};"
            " no next neighbor to join with"
        )
    next_start = min(other.attrs["start"] for other in later)
    following = [other.id for other in later if other.attrs["start"] == next_start]
    if next_start != end:
        return Outcome(
            False,
            f"joined_with_next=true but next range on row {row!r} starts at"
            f" {float(next_start)} (must equal {float(end)} for ranges to join)",
            following,
        )
    if joined not in following:
        return Outcome(
            False,
            "joined_with_next=true but the range it joins isn't the next range"
            f" on row {row!r}",
            following,
        )
    return None


def _qt_reads(text: str) -> bool:
    """Whether Qt reads `text` as a color, as `QColor(text).isValid()` says."""
    if text.startswith("#"):
        digits = text[1:]
        return len(digits) in _HEX_LENGTHS and all(c in _HEX_DIGITS for c in digits)
    # Qt reads a name of up to 255 UTF-16 units, in any case, leaving out spaces
    # and tabs. A NUL, or a character beyond Latin-1, ends it.
    if len(text.encode("utf-16-le")) // 2 > 255:
        return False
    name = []
    for character in text:
        if character in " \t":
            continue
        if character == "\0" or ord(character) > 0xFF:
            break
        name.append(character.lower())
    return "".join(name) in _COLOR_NAMES


def _media_time(seconds: float) -> str:
    """A time as TiLiA's `format_media_time` shows it ("01:05.0", "1:02:05.0"),
    with a minus sign before a negative one ("-00:01.0"). It is rounded to tenths
    before its minutes are counted, so 59.96 is "01:00.0", not "00:60.0"."""
    if seconds < 0:
        return "-" + _media_time(-seconds)
    seconds = float(f"{seconds:.1f}")
    seconds_and_fraction = f"{seconds % 60:.1f}".zfill(4)
    minutes = int(seconds // 60)
    hours = f"{minutes // 60}:" if minutes >= 60 else ""
    return f"{hours}{str(minutes % 60).zfill(2)}:{seconds_and_fraction}"


def _is_number(value: Any) -> bool:
    """A finite number, as JSON stores one: not a bool, nan, an infinity, or an
    integer too large for a float."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _is_comparable(value: Any) -> bool:
    """A number another can be compared with: an integer of any size, or a
    finite float. A component that breaks a rule with one is still compared."""
    return _is_integer(value) or _is_number(value)


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_row_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == ROW_ID_LENGTH
        and all(c in ROW_ID_CHARACTERS for c in value)
    )


def _shown(value: Any) -> str:
    """`value` as a reason shows it. An integer Python won't turn into text, one
    of more than 4,300 digits unless set otherwise, is named instead."""
    try:
        return f"{value}"
    except ValueError:
        return "an integer too long to show"


def _broken(reason: str) -> Outcome:
    return Outcome(False, reason)
