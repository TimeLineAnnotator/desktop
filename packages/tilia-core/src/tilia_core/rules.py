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

`check_timeline` checks a whole timeline at once with the same rules, finding
for each component the others that matter rather than comparing it with every
one: an import checks its components with it once, before it commits, and so
do reading and writing a file, and a single change, on the timeline it leaves.

A harmony's quality and inversion and a mode's type are checked against the
installed music21, as TiLiA checks them, so checking a harmony or a mode needs
the `harmony` extra. Without it, the other rules are checked, and when none is
broken, `CantCheck` is raised, before the color is checked: a bad color mustn't
hide that a rule couldn't be checked. music21 is imported only when a harmony or
a mode is checked, or a quality's inversions are counted.

A broken rule gives a code along with its reason. The reason is for reading: it
quotes values, a time or a row's name, and reads otherwise when they change. The
code says which rule it is, and doesn't change. So it is what tells one problem
from another, and a program can go by it, where the reasons are free to read
better.
"""

from __future__ import annotations

import bisect
import importlib.util
import itertools
import math
import string
from collections.abc import (
    Callable,
    Collection,
    Iterable,
    Iterator,
    Mapping,
    Sequence,
)
from dataclasses import dataclass
from types import ModuleType
from typing import TYPE_CHECKING, Any, cast

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
# since 43a61224, 28539120 and 6989db60. TiLiA takes them from here once it checks
# with the rules. The cadential six-four's sixth and fourth aren't added tones, but
# it is written and typed as if they were, on the major triad.
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
    "cadential-six-four": ("major", "64"),
    "minor-added-ninth": ("minor", "9"),
    "minor-seventh-added-eleventh": ("minor-seventh", "11"),
}
# Qualities TiLiA keeps in root position, whatever their intervals:
# `get_inversion_amount` gives 0 for them. TiLiA takes them from here once it
# checks with the rules.
#
# These qualities are locked to root position: the Inspector/Add Harmony
# dialog offer no inversion choices for them, and to_roman_numeral /
# letter_symbol_label render a fixed string regardless of bass note.
#
# - Italian, French, German (augmented sixths): genuinely have no inversions
#   in standard tonal harmony — the augmented-sixth interval that defines
#   the chord only exists with scale degree b6 in the bass.
# - Tristan: referenced in the literature as a single fixed sonority,
#   not a chord family with an established inversion convention.
# - Neapolitan: DOES have real inversions (root position and 2nd inversion
#   occur, though 1st inversion — "N6" — is by far the most common). But
#   music21's own "Neapolitan"/"N6" CHORD_TYPES entry is not the classical
#   Neapolitan-sixth triad at all — it's an unrelated 4-note "all-interval
#   tetrachord" that happens to share the abbreviation. Supporting inversions
#   here means building the real major-triad-on-b2 pitches first, not just
#   removing this quality from the set below.
# - power: DOES have a real inverted voicing (5th in the bass, common in
#   rock/metal), but music21.harmony.ChordSymbol can't construct it via
#   inversion=1 (raises ChordException — see the try/except in
#   HarmonyUI.letter_symbol), and there's no established figured-bass
#   notation for an inverted power chord to reuse in to_roman_numeral.
# - cadential six-four: its root, the dominant, is in the bass by definition.
#   With another tone in the bass, it is a different chord.
#
# TODO: Neapolitan and power are the two qualities above actually worth
# revisiting (Italian/French/German/Tristan have no inversions to support).
# Neapolitan needs its pitches constructed independently of music21's
# "N6" chord type before inversions mean anything; power needs a bass
# override in HarmonyUI.letter_symbol (music21 can't invert it directly)
# plus an invented figured-bass notation for to_roman_numeral, since no
# textbook convention exists for an inverted power chord.
NO_INVERSION_QUALITIES = frozenset(
    {
        "Italian",
        "French",
        "German",
        "Neapolitan",
        "Tristan",
        "power",
        "cadential-six-four",
    }
)

# Two hierarchy boundaries count as the same when they are within 1e-9 s of each
# other, or within a billionth of the larger, whichever is more: `math.isclose`
# with this `abs_tol` and its default `rel_tol` of 1e-9, as TiLiA's
# `get_boundary_conflicts` compares them since `dev`'s 2ceec157. So below 1 s they
# meet within 1e-9 s, and at an hour within 3.6e-6 s. Files TiLiA saved before then
# hold boundaries a few ulps apart where they should meet.
_TIME_ABS_TOL = 1e-9

# The names TiLiA's reasons give the point kinds (their `frontend_name`).
_POINT_NAMES = {
    "marker": "marker",
    "harmony": "harmony",
    "mode": "mode",
    "beat": "beat",
    "pdf_marker": "PDF page marker",
}
_POINT_KINDS = tuple(_POINT_NAMES)
# The kinds whose rules read music21.
_NEED_MUSIC21 = ("harmony", "mode")

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

# The rules' codes. A value that isn't one has `bad_code(attribute)`, whatever the
# kind and whatever its reason says.
NEGATIVE_TIME = "negative_time"
PAST_MEDIA_END = "past_media_end"
SAME_TIME = "same_time"
SAME_PLACE = "same_place"
CROSSING = "crossing"
NO_SUCH_PAGE = "no_such_page"
END_NOT_AFTER_START = "end_not_after_start"
PRE_START_AFTER_START = "pre_start_after_start"
POST_END_BEFORE_END = "post_end_before_end"
UNKNOWN_ROW = "unknown_row"
BAD_JOIN = "bad_join"
SAME_ROW_ID = "same_row_id"
NEGATIVE_MEASURE_NUMBER = "negative_measure_number"


class _AtOdds:
    """The ids of the others a component is at odds with, in the order given, each
    found as it is asked for. There is at least one."""

    def __iter__(self) -> Iterator[str]:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError

    def __contains__(self, other: object) -> bool:
        raise NotImplementedError

    def naming(self, limit: int, named: Collection[str]) -> tuple[list[str], int]:
        """The first `limit` of them that aren't in `named`, and how many more
        aren't."""
        left = (other for other in self if other not in named)
        kept = list(itertools.islice(left, limit))
        return kept, len(self) - sum(other in self for other in named) - len(kept)


class Outcome(tuple[bool, str]):
    """What checking the rules gives: `(True, "")`, or `(False, reason)`.

    It is true when no rule is broken, so `if rules.marker(...):` reads as "the
    marker keeps to the rules"; it also unpacks as `ok, reason`. `others` are
    the ids of the other components a broken rule is about: those at the same
    time or place, the hierarchies it crosses, the ranges it should join, found
    when they are first asked for where they are many. `naming` gives the first
    of them and how many more there are, without finding the rest. `code`
    says which rule it is, in words that don't change with the values its reason
    quotes. `about` says what of the component the rule checks, where one code
    is given by rules about different attributes of one component: "start" and
    "pre_start" can both be negative, and "time", a hierarchy's "start end"
    (one rule, whichever of the two it is), "end" and "post_end" can be past the
    media's end. Its code and `about` tell one component's problems apart. It is
    "" where the code says it all.
    """

    # Read through `others`, `code` and `about`, which can't be set: every outcome
    # that keeps to the rules is the one `OK`. A tuple's subclass can't give it a
    # slot.
    _others: tuple[str, ...] | _AtOdds
    _code: str
    _about: str

    def __new__(
        cls,
        ok: bool,
        reason: str = "",
        others: Iterable[str] = (),
        code: str = "",
        about: str = "",
    ) -> Outcome:
        outcome = super().__new__(cls, (bool(ok), reason))
        outcome._others = others if isinstance(others, _AtOdds) else tuple(others)
        outcome._code = code
        outcome._about = about
        return outcome

    def __bool__(self) -> bool:
        return self[0]

    def __getnewargs__(self) -> tuple[bool, str, tuple[str, ...], str, str]:  # type: ignore[override]
        # What copy and pickle give __new__: a tuple's would be the pair alone.
        return self[0], self[1], self.others, self._code, self._about

    @property
    def others(self) -> tuple[str, ...]:
        if isinstance(self._others, _AtOdds):
            self._others = tuple(self._others)
        return self._others

    def naming(
        self, limit: int, named: Collection[str] = ()
    ) -> tuple[list[str], int, bool]:
        """The first `limit` of `others`, in order, that aren't in `named`, how many
        more of them aren't either, and whether there are any others at all. As
        listing them gives it, but in far less time where they are thousands."""
        others = self._others
        if isinstance(others, _AtOdds):
            kept, more = others.naming(limit, named)
            return kept, more, True
        left = [other for other in others if other not in named]
        return left[:limit], max(0, len(left) - limit), len(others) > 0

    @property
    def about(self) -> str:
        return self._about

    @property
    def code(self) -> str:
        return self._code

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


# Each kind's rules but the color are one private function, which gives a check
# for each rule, in the order the rules list them. `_RULES` names it for its kind,
# and the kind's public function and `check_timeline` both find it there, so that
# there is one set of rules. `_first` gives the first rule broken, or None. `_kept`
# then raises `CantCheck` when the rules that need music21 couldn't be checked, and
# only then checks the color: an importer keeps a row whose color isn't one, with
# the default color, so a bad color mustn't hide another broken rule, nor that a
# rule couldn't be checked.

Check = Callable[[], "Outcome | None"]


def _first(checks: Iterable[Check]) -> Outcome | None:
    """The first rule `checks` find broken, each checked only once the ones
    before it are kept; or None."""
    for check in checks:
        broken = check()
        if broken is not None and not broken:
            return broken
    return None


def _first_and_rest(
    checks: Sequence[Check], every: bool
) -> tuple[Outcome | None, tuple[Outcome, ...]]:
    """`_first`'s outcome, and, when `every`, the others `checks` find broken after
    it, each check made once. The first check is that the times are numbers and the
    texts text: when it finds one that isn't, the others, which compare them, aren't
    made."""
    for at, check in enumerate(checks):
        broken = check()
        if broken is not None and not broken:
            if not every or at == 0:
                return broken, ()
            later = (later_check() for later_check in checks[at + 1 :])
            return broken, tuple(o for o in later if o is not None and not o)
    return None, ()


def _kept(
    attrs: Mapping[str, Any],
    broken: Outcome | None,
    cant_check: CantCheck | None = None,
) -> Outcome:
    """`broken`, the first rule found broken but the color, else `cant_check`
    raised, when the rules that need music21 couldn't be checked, else the
    color's outcome."""
    if broken is not None:
        return broken
    if cant_check is not None:
        raise cant_check from cant_check.error
    broken = _color_of(attrs)
    return OK if broken is None else broken


def marker(
    media_length: float, others: Iterable[tla.Component], attrs: Mapping[str, Any]
) -> Outcome:
    """A marker."""
    return _checked("marker", media_length, others, attrs)


def beat(
    media_length: float, others: Iterable[tla.Component], attrs: Mapping[str, Any]
) -> Outcome:
    """A beat. Its measure mark and beat unit follow the measure table's rules."""
    return _checked("beat", media_length, others, attrs)


def pdf_marker(
    media_length: float,
    others: Iterable[tla.Component],
    attrs: Mapping[str, Any],
    *,
    page_count: int,
) -> Outcome:
    """A PDF marker, in a PDF of `page_count` pages: 0 for a PDF that can't be read."""
    return _checked("pdf_marker", media_length, others, attrs, page_count=page_count)


def harmony(
    media_length: float, others: Iterable[tla.Component], attrs: Mapping[str, Any]
) -> Outcome:
    """A harmony. Without music21, raises `CantCheck` when no rule but the color is
    broken: the color is checked after it."""
    return _checked("harmony", media_length, others, attrs)


def mode(
    media_length: float, others: Iterable[tla.Component], attrs: Mapping[str, Any]
) -> Outcome:
    """A key. Without music21, raises `CantCheck` when no rule but the color is
    broken: the color is checked after it."""
    return _checked("mode", media_length, others, attrs)


def hierarchy(
    media_length: float, others: Iterable[tla.Component], attrs: Mapping[str, Any]
) -> Outcome:
    """A hierarchy. Hierarchies nest: one that overlaps another lies inside it,
    at a lower level."""
    return _checked("hierarchy", media_length, others, attrs)


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
    return _checked("range", media_length, others, attrs, rows=rows)


def _checked(
    kind: str,
    media_length: float,
    others: Iterable[tla.Component],
    attrs: Mapping[str, Any],
    *,
    page_count: int = 0,
    rows: Sequence[Mapping[str, Any]] = (),
) -> Outcome:
    """What a kind's public function gives: its rules, from `_RULES`, then
    `CantCheck`, then the color."""
    music21: ModuleType | None = None
    cant_check = None
    if kind in _NEED_MUSIC21:
        music21, error = _music21()
        if music21 is None:
            cant_check = CantCheck(kind, error)
    context = _Context(page_count=page_count, rows=rows, music21=music21)
    checks = _RULES[kind](media_length, others, attrs, context)
    return _kept(attrs, _first(checks), cant_check)


class _Context:
    """What a kind's rules read besides the component and the others: the PDF's
    page count, the range timeline's rows and their ids, and music21, which is
    None without it."""

    def __init__(
        self,
        *,
        page_count: float = 0,
        rows: Sequence[Mapping[str, Any]] = (),
        music21: ModuleType | None = None,
    ) -> None:
        self.page_count = page_count
        self.rows = rows
        self.row_ids = _RowIds([row.get("id") for row in rows])
        self.music21 = music21


class _RowIds:
    """The ids of a timeline's rows. `in` finds what it finds in a list of them,
    but in a set, since a timeline may have thousands. It goes to the list when one
    of them can't go in a set, as in a broken file, and for a value that can't be
    looked up in one."""

    def __init__(self, ids: list[Any]) -> None:
        self._ids = ids
        self._lookup: Collection[Any]
        try:
            self._lookup = frozenset(ids)
        except TypeError:
            self._lookup = ids

    def __contains__(self, row_id: Any) -> bool:
        try:
            return row_id in self._lookup
        except TypeError:
            return row_id in self._ids


def _marker(
    media_length: float,
    others: Iterable[tla.Component],
    attrs: Mapping[str, Any],
    context: _Context,
) -> Sequence[Check]:
    return _point("marker", media_length, others, attrs)


def _beat(
    media_length: float,
    others: Iterable[tla.Component],
    attrs: Mapping[str, Any],
    context: _Context,
) -> Sequence[Check]:
    return (
        *_point("beat", media_length, others, attrs),
        lambda: _measure_number(attrs.get("measure")),
    )


def _measure_number(measure: Any) -> Outcome | None:
    """A measure mark's number, when it has one, is from 0: a pickup is 0, and
    TiLiA's "Set measure number" asks for no less."""
    number = measure.get("number") if isinstance(measure, Mapping) else None
    if _is_integer(number) and number < 0:
        return _broken(
            NEGATIVE_MEASURE_NUMBER,
            f"Measure number can't be below 0. Got '{_shown(number)}'",
        )
    return None


def _pdf_marker(
    media_length: float,
    others: Iterable[tla.Component],
    attrs: Mapping[str, Any],
    context: _Context,
) -> Sequence[Check]:
    """A PDF marker's rules, in a PDF of `context.page_count` pages."""
    return (
        *_point("pdf_marker", media_length, others, attrs),
        lambda: _page(attrs.get("page_number"), context.page_count),
    )


def _harmony(
    media_length: float,
    others: Iterable[tla.Component],
    attrs: Mapping[str, Any],
    context: _Context,
) -> Sequence[Check]:
    """A harmony's rules; without music21, those that don't need it."""
    music21 = context.music21
    return (
        *_point("harmony", media_length, others, attrs),
        lambda: _one_of(attrs, "step", _STEPS),
        lambda: _one_of(attrs, "applied_to", _STEPS),
        lambda: _one_of(attrs, "accidental", HARMONY_ACCIDENTALS),
        lambda: _quality_and_inversion(music21, attrs) if music21 else None,
        lambda: _one_of(attrs, "level", _LEVELS),
        lambda: _one_of(attrs, "display_mode", HARMONY_DISPLAY_MODES),
        lambda: _one_of(attrs, "custom_text_font_type", FONT_TYPES),
    )


def _mode(
    media_length: float,
    others: Iterable[tla.Component],
    attrs: Mapping[str, Any],
    context: _Context,
) -> Sequence[Check]:
    """A key's rules; without music21, those that don't need it."""
    music21 = context.music21
    return (
        *_point("mode", media_length, others, attrs),
        lambda: _one_of(attrs, "step", _STEPS),
        lambda: _one_of(attrs, "accidental", HARMONY_ACCIDENTALS),
        lambda: _mode_type(music21, attrs) if music21 else None,
        lambda: _one_of(attrs, "level", _LEVELS),
    )


def _hierarchy(
    media_length: float,
    others: Iterable[tla.Component],
    attrs: Mapping[str, Any],
    context: _Context,
) -> Sequence[Check]:
    start, end, level = attrs.get("start"), attrs.get("end"), attrs.get("level")
    found: list[list[tla.Component]] = []

    def hierarchies() -> list[tla.Component]:
        # Read from `others` once, when a rule between hierarchies first asks.
        if not found:
            found.append([other for other in others if other.kind == "hierarchy"])
        return found[0]

    return (
        lambda: _every_kind(attrs, _SEGMENT_TIMES),
        lambda: _hierarchy_in_media(start, end, media_length),
        lambda: _hierarchy_start(start),
        lambda: _hierarchy_end(start, end),
        lambda: _hierarchy_level(level),
        *_margins(attrs, start, end, media_length),
        lambda: _same_place(start, end, level, hierarchies()),
        lambda: _crossed(start, end, level, hierarchies()),
    )


def _range(
    media_length: float,
    others: Iterable[tla.Component],
    attrs: Mapping[str, Any],
    context: _Context,
) -> Sequence[Check]:
    """A range's rules, in a timeline whose rows are `context.rows`."""
    start, end = attrs.get("start"), attrs.get("end")
    return (
        lambda: _every_kind(attrs, _SEGMENT_TIMES),
        lambda: _range_row(attrs.get("row_id"), context.row_ids),
        lambda: _range_times(start, end),
        lambda: _range_start(start),
        lambda: _range_end(end, media_length),
        *_margins(attrs, start, end, media_length),
        lambda: _joined(attrs, others, context.rows),
    )


def _margins(
    attrs: Mapping[str, Any], start: float, end: float, media_length: float
) -> tuple[Check, ...]:
    """The rules of a hierarchy's or a range's `pre_start` and `post_end`, each
    rule a check of its own, so that every rule broken is found: a pre_start
    before 0 can be after a start before it too, and a post_end past the end
    before an end past it."""
    pre_start, post_end = attrs.get("pre_start"), attrs.get("post_end")
    return (
        lambda: _pre_start_in_media(pre_start),
        lambda: _pre_start_by_start(pre_start, start),
        lambda: _post_end_in_media(post_end, media_length),
        lambda: _post_end_by_end(post_end, end),
    )


Rules = Callable[
    [float, Iterable["tla.Component"], Mapping[str, Any], _Context], Sequence[Check]
]
# Each kind's rules: the one place a kind finds them.
_RULES: dict[str, Rules] = {
    "marker": _marker,
    "beat": _beat,
    "pdf_marker": _pdf_marker,
    "harmony": _harmony,
    "mode": _mode,
    "hierarchy": _hierarchy,
    "range": _range,
}
# The kinds these rules cover.
KINDS = tuple(_RULES)


def range_rows(rows: Sequence[Mapping[str, Any]]) -> Outcome:
    """A range timeline's rows: each with its own id of six letters and digits,
    a name, and a color or none."""
    ids: set[str] = set()
    for row in rows:
        row_id = row.get("id")
        if not _is_row_id(row_id):
            return _not_valid("row_id", row_id)
        if row_id in ids:
            return _broken(SAME_ROW_ID, f"There is already a row with the id {row_id}.")
        ids.add(row_id)
        name = row.get("name")
        if not isinstance(name, str):
            return _not_valid("row_name", name)
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
    if value is None or (isinstance(value, str) and not value):
        return OK
    if isinstance(value, str) and _qt_reads(value):
        return OK
    return _not_valid("color", value)


def media_length(value: Any) -> Outcome:
    """A media length: a positive, finite number, or None when it is unknown."""
    if value is None or (_is_number(value) and value > 0):
        return OK
    return _not_valid("media_length", value)


def cant_check(kind: str) -> CantCheck | None:
    """What a component of `kind` can't be checked for, when its rules need music21
    and music21 is missing or won't import; or None."""
    if kind not in _NEED_MUSIC21:
        return None
    music21, error = _music21()
    if music21 is not None:
        return None
    unable = CantCheck(kind, error)
    unable.__cause__ = error
    return unable


def split_added_tone(quality: str) -> tuple[str, str]:
    """A quality's base quality and added tone, or the quality and ""."""
    return ADDED_TONE_QUALITIES.get(quality, (quality, ""))


def get_inversion_amount(quality: str) -> int:
    """A quality's number of inversions, as TiLiA counts them: those of its chord
    type in the installed music21, but none for `NO_INVERSION_QUALITIES`. An
    added-tone quality has its base quality's, since an added tone isn't one the
    chord can be inverted to.

    Raises `ValueError` for a value that isn't a quality, with TiLiA's text, and
    `CantCheck` when music21 is missing or won't import.
    """
    music21, error = _music21()
    if music21 is None:
        raise CantCheck("harmony", error) from error
    if not _is_quality(music21, quality):
        raise ValueError(f'Invalid harmony quality "{_shown(quality)}"')
    return _inversions(music21, quality)


def not_valid(attribute: str, value: Any) -> str:
    """The reason for a value of `attribute` that isn't one, for every kind.

    The rules give it for a value they refuse as not being one, such as a time of
    nan, and the importers for a value they can't read, so the two read alike. An
    empty string is named, so that the text doesn't start with a space. A string
    of only whitespace isn't: only the CSV reader makes such a cell empty.
    """
    shown = "an empty value" if isinstance(value, str) and not value else _shown(value)
    return f"{shown} is not a valid {attribute.replace('_', ' ')}."


def bad_code(attribute: str) -> str:
    """The code of the rule that `attribute` holds a value that is one."""
    return f"bad_{attribute}"


@dataclass(frozen=True)
class Checked:
    """What `check_timeline` finds for one component.

    `outcome` is what its kind's function gives, but for the color: the first
    other rule broken, else `OK`. `color` is the color's own outcome, whatever
    else is broken, so that an importer can keep the component with the default
    color, and a reader can warn about both. `cant_check`, for a harmony or a key
    that breaks no rule but its color, is the `CantCheck` its kind's function
    raises when music21 is missing or won't import: the rules that need it
    couldn't be checked. `also` is, with `check_timeline`'s `every_rule`, the
    other rules it breaks but the color, after the one in `outcome`.
    """

    outcome: Outcome
    color: Outcome = OK
    cant_check: CantCheck | None = None
    also: tuple[Outcome, ...] = ()


def check_timeline(
    media_length: float,
    components: Iterable[tla.Component],
    *,
    rows: Sequence[Mapping[str, Any]] | None = None,
    page_count: float | None = None,
    skip_broken: bool = False,
    every_rule: bool = False,
) -> dict[str, Checked]:
    """A timeline's components, each checked with the others, in one pass.

    Each component is checked by its kind's rules, as its kind's function checks
    it, with the same reasons. By default each is checked with every other one,
    as reading or writing a file checks them, and as a single change is checked:
    on the timeline it leaves, since it can break another component's rule, such
    as a join. With `skip_broken`, they are checked as an import checks them: in
    the order given, each with the earlier ones kept, so that one that breaks a
    rule is left out of what follows. One whose only broken rule is its color is
    kept, as an importer keeps it with the default color, and so is one whose
    rules couldn't be checked without music21.

    With `every_rule`, which reading and writing a file ask for, a component that
    breaks a rule is checked by all its rules, and those after the first are in
    `also`. An import stops at the first, so it can't ask for this.

    Ranges need the timeline's `rows`, and PDF markers the PDF's `page_count`,
    which `math.inf` leaves unchecked but for its lower bound, for a caller that
    doesn't read the PDF. music21 is looked up once, for the first harmony or key.

    Gives what is found for each component, by its id, in the order given. A
    component of a kind these rules don't cover isn't in it, and isn't compared
    with the others.

    Rather than compare each component with every other one, it finds those
    whose rules a component could break: the points at its time, the
    hierarchies that overlap it (by the order of their starts), the ranges that
    come next in its row. So n components take about n log n, plus the others
    found. Where they are many, as when thousands are at one time, an outcome finds
    them only as they are asked for (`Outcome.others`), but an import's finds them
    all: its components are checked with those kept so far, not with every one.
    """
    if skip_broken and every_rule:
        raise ValueError("every_rule is for a timeline checked with every component")
    components = list(components)
    _needed(components, rows, page_count)
    kinds = _Kinds(media_length, rows or (), page_count or 0)
    others = _Others(components, every=not skip_broken)
    covered = [
        place for place, component in enumerate(components) if component.kind in KINDS
    ]
    if not skip_broken:
        for place in covered:
            others.add(place)
    found: dict[str, Checked] = {}
    for place in covered:
        component = components[place]
        kind, attrs = component.kind, component.attrs
        with_others = others.of(place)
        broken, also, unable = kinds.broken(kind, attrs, with_others, every_rule)
        if broken is not None:
            broken = with_others.complete(broken)
            also = tuple(with_others.complete(outcome) for outcome in also)
        found[component.id] = _found(attrs, broken, unable, also)
        if skip_broken and broken is None:
            others.add(place)
    return found


def _found(
    attrs: Mapping[str, Any],
    broken: Outcome | None,
    unable: CantCheck | None,
    also: tuple[Outcome, ...] = (),
) -> Checked:
    color_outcome = _color_of(attrs)
    return Checked(
        OK if broken is None else broken,
        OK if color_outcome is None else color_outcome,
        unable,
        also,
    )


def _point(
    kind: str,
    media_length: float,
    others: Iterable[tla.Component],
    attrs: Mapping[str, Any],
) -> Sequence[Check]:
    """The rules for every kind, the time's bounds, and no other at the same time."""
    time = attrs.get("time")
    return (
        lambda: _every_kind(attrs, ("time",)),
        lambda: _time_not_negative(time),
        lambda: _time_in_media(time, media_length),
        lambda: _same_time(kind, time, others),
    )


def _time_not_negative(time: float) -> Outcome | None:
    if time < 0:
        return _broken(
            NEGATIVE_TIME,
            f"Time can't be negative. Got '{_media_time(time)}'",
            about="time",
        )
    return None


def _time_in_media(time: float, media_length: float) -> Outcome | None:
    if time > media_length:
        return _broken(
            PAST_MEDIA_END,
            f"Time '{_media_time(time)}' is bigger than media time"
            f" '{_media_time(media_length)}'",
            about="time",
        )
    return None


def _same_time(
    kind: str, time: float, others: Iterable[tla.Component]
) -> Outcome | None:
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
            SAME_TIME,
        )
    return None


def _every_kind(attrs: Mapping[str, Any], times: Iterable[str]) -> Outcome | None:
    """Times are finite numbers and texts are text. The color is checked last."""
    for name in times:
        value = attrs.get(name)
        if value is None and name in _UNSET_TIMES:
            continue
        if not _is_number(value):
            return _not_valid(name, value)
    for name in _TEXTS:
        if name in attrs and not isinstance(attrs[name], str):
            return _not_valid(name, attrs[name])
    return None


def _color_of(attrs: Mapping[str, Any]) -> Outcome | None:
    if "color" in attrs:
        outcome = color(attrs["color"])
        if not outcome:
            return outcome
    return None


def _page(page_number: Any, page_count: float) -> Outcome | None:
    if not _is_integer(page_number):
        return _not_valid("page_number", page_number)
    if not 1 <= page_number <= page_count:
        return _broken(NO_SUCH_PAGE, "The PDF has no page with that number.")
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
    return _not_valid(name, value)


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
    if not _is_quality(music21, quality):
        return _not_valid("quality", quality)
    inversion = attrs.get("inversion", 0)
    if not (_is_integer(inversion) and 0 <= inversion <= _inversions(music21, quality)):
        return _not_valid("inversion", inversion)
    return None


def _is_quality(music21: ModuleType, quality: Any) -> bool:
    return (
        isinstance(quality, str)
        and split_added_tone(quality)[0] in music21.harmony.CHORD_TYPES
    )


def _inversions(music21: ModuleType, quality: str) -> int:
    """`get_inversion_amount` of a quality that is one, with music21 already looked
    up: `check_timeline` looks it up once, whatever the harmonies."""
    if quality in NO_INVERSION_QUALITIES:
        return 0
    quality, _ = split_added_tone(quality)
    intervals = str(music21.harmony.CHORD_TYPES[quality][0])
    return len(intervals.split(",")) - 1


def _mode_type(music21: ModuleType, attrs: Mapping[str, Any]) -> Outcome | None:
    """The type is one of music21's `modeSharpsAlter`, but ionian and aeolian."""
    types = [
        name for name in music21.key.modeSharpsAlter if name not in _NOT_MODE_TYPES
    ]
    return _one_of(attrs, "type", types)


def _hierarchy_in_media(
    start: float, end: float, media_length: float
) -> Outcome | None:
    # The values are compared as they are given, as `_time_in_media` compares them,
    # so a media length too large for a float is longer than any time. TiLiA shows
    # them as floats, and so do the reasons, but for such a length, which is shown
    # as it is.
    if not (start > media_length or end > media_length):
        return None
    length = float(media_length) if _is_number(media_length) else _shown(media_length)
    if start > media_length:
        return _broken(
            PAST_MEDIA_END,
            f"Start time '{float(start)}' is bigger than media time '{length}'",
            about="start end",
        )
    return _broken(
        PAST_MEDIA_END,
        f"End time '{float(end)}' is bigger than media time '{length}'",
        about="start end",
    )


def _hierarchy_start(start: float) -> Outcome | None:
    if start < 0:
        return _broken(
            NEGATIVE_TIME,
            f"Start time can't be negative. Got '{float(start)}'",
            about="start",
        )
    return None


def _hierarchy_end(start: float, end: float) -> Outcome | None:
    if end <= start:
        return _broken(
            END_NOT_AFTER_START,
            f"End time '{float(end)}' should be bigger than start time"
            f" '{float(start)}'",
        )
    return None


def _hierarchy_level(level: Any) -> Outcome | None:
    if not _is_integer(level):
        return _not_valid("level", level)
    if level < 1:
        return _broken(
            bad_code("level"), f"Level can't be below 1. Got '{_shown(level)}'"
        )
    return None


def _pre_start_in_media(pre_start: float | None) -> Outcome | None:
    """`pre_start`, when set, is from 0."""
    if pre_start is not None and pre_start < 0:
        return _broken(
            NEGATIVE_TIME, "pre_start is outside media bounds.", about="pre_start"
        )
    return None


def _pre_start_by_start(pre_start: float | None, start: float) -> Outcome | None:
    """`pre_start`, when set, is no later than the start."""
    if pre_start is not None and pre_start > start:
        return _broken(PRE_START_AFTER_START, "pre_start can't be after start time.")
    return None


def _post_end_in_media(post_end: float | None, media_length: float) -> Outcome | None:
    """`post_end`, when set, is no later than the media length."""
    if post_end is not None and post_end > media_length:
        return _broken(
            PAST_MEDIA_END, "post_end is outside media bounds.", about="post_end"
        )
    return None


def _post_end_by_end(post_end: float | None, end: float) -> Outcome | None:
    """`post_end`, when set, is no earlier than the end."""
    if post_end is not None and post_end < end:
        return _broken(POST_END_BEFORE_END, "post_end can't be before end time.")
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
            SAME_PLACE,
        )
    return None


def _crossed(
    start: float, end: float, level: int, hierarchies: Iterable[tla.Component]
) -> Outcome | None:
    if not _is_comparable(level):
        return None
    crossed = [
        other.id for other in hierarchies if _cross(start, end, level, other.attrs)
    ]
    if crossed:
        return Outcome(
            False, "Component would overlap with existing component.", crossed, CROSSING
        )
    return None


def _cross(start: float, end: float, level: int, other: Mapping[str, Any]) -> bool:
    """Whether two hierarchies overlap, and neither lies inside the other, lower.

    This is when TiLiA's `get_boundary_conflicts` finds a conflict between them, as
    `dev` has it since 2ceec157: two boundaries `_times_close` finds close count as
    the same.
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
    """Whether two times count as the same, as TiLiA's `_times_close` says: within
    `_TIME_ABS_TOL`, or within a billionth of the larger, whichever is more."""
    try:
        return math.isclose(a, b, abs_tol=_TIME_ABS_TOL)
    except OverflowError:  # an integer too large for a float is close only to itself
        return a == b


def _le(a: float, b: float) -> bool:
    return a < b or _times_close(a, b)


def _lt(a: float, b: float) -> bool:
    return a < b and not _times_close(a, b)


def _range_row(row_id: Any, row_ids: _RowIds) -> Outcome | None:
    if not row_id or row_id not in row_ids:
        return _broken(UNKNOWN_ROW, "Invalid row ID.")
    return None


def _range_times(start: float, end: float) -> Outcome | None:
    if start >= end:
        return _broken(END_NOT_AFTER_START, "Start time must be before end time.")
    return None


def _range_start(start: float) -> Outcome | None:
    """A range's start is from 0. TiLiA checks it with the end, in one text, but
    they are two rules: a range before 0 can be past the end too."""
    if start < 0:
        return _broken(NEGATIVE_TIME, "Range is outside media bounds.", about="start")
    return None


def _range_end(end: float, media_length: float) -> Outcome | None:
    """A range's end is no later than the media length."""
    if end > media_length:
        return _broken(PAST_MEDIA_END, "Range is outside media bounds.", about="end")
    return None


def _joined(
    attrs: Mapping[str, Any],
    others: Iterable[tla.Component],
    rows: Sequence[Mapping[str, Any]],
) -> Outcome | None:
    """`joined_right`, when set, is a next range in the row, starting at this one's end.

    The next ranges are those of the row that start first after this one starts.
    The reasons are the range importer's (`_apply_pending_joins`). They differ by
    what comes next in the row, but it is one rule, with one code.
    """
    joined = attrs.get("joined_right")
    if joined is None:
        return None
    row_id, start, end = attrs.get("row_id"), attrs["start"], attrs["end"]
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
            BAD_JOIN,
            f"joined_with_next=true on last range of row {row!r};"
            " no next neighbor to join with",
        )
    next_start = min(other.attrs["start"] for other in later)
    following = [other.id for other in later if other.attrs["start"] == next_start]
    if next_start != end:
        return Outcome(
            False,
            f"joined_with_next=true but next range on row {row!r} starts at"
            f" {float(next_start)} (must equal {float(end)} for ranges to join)",
            following,
            BAD_JOIN,
        )
    if joined not in following:
        return Outcome(
            False,
            "joined_with_next=true but the range it joins isn't the next range"
            f" on row {row!r}",
            following,
            BAD_JOIN,
        )
    return None


def _needed(
    components: Sequence[tla.Component],
    rows: Sequence[Mapping[str, Any]] | None,
    page_count: int | None,
) -> None:
    """Refuses components with one id, as no timeline has them, and ranges without
    rows or PDF markers without a page count, which every one would break."""
    ids: set[str] = set()
    for component in components:
        if component.id in ids:
            raise ValueError(f"two components have the id {component.id!r}")
        ids.add(component.id)
        if component.kind == "range" and rows is None:
            raise TypeError("checking ranges needs the timeline's rows")
        if component.kind == "pdf_marker" and page_count is None:
            raise TypeError("checking PDF markers needs the PDF's page count")


class _Kinds:
    """Each kind's rules, from `_RULES`, as `check_timeline` checks a timeline
    with them."""

    def __init__(
        self,
        media_length: float,
        rows: Sequence[Mapping[str, Any]],
        page_count: float,
    ) -> None:
        self._media_length = media_length
        self._context = _Context(page_count=page_count, rows=rows)
        # music21, looked up for the first harmony or key only, and not kept
        # once the timeline is checked, so that installing it takes effect.
        self._music21: tuple[ModuleType | None, Exception | None] | None = None

    def broken(
        self,
        kind: str,
        attrs: Mapping[str, Any],
        others: Iterable[tla.Component],
        every: bool,
    ) -> tuple[Outcome | None, tuple[Outcome, ...], CantCheck | None]:
        """The first rule but the color that a component of `kind` with `attrs`
        breaks, or None; when `every`, the other rules it breaks after that; and when
        it breaks none, whether the rules that need music21 couldn't be checked."""
        error = None
        if kind in _NEED_MUSIC21:
            if self._music21 is None:
                self._music21 = _music21()
                self._context.music21 = self._music21[0]
            error = self._music21[1]
        rules = _RULES[kind]
        checks = rules(self._media_length, others, attrs, self._context)
        broken, also = _first_and_rest(checks, every)
        if broken is None and kind in _NEED_MUSIC21 and self._context.music21 is None:
            # The cause the kind's function raises it from.
            unable = CantCheck(kind, error)
            unable.__cause__ = error
            return None, (), unable
        return broken, also, None


# How many others a component is compared with one by one when a timeline is read.
# Thousands at odds with each other are too many to list for each of them, so past
# this many, they are found together: as a group they are in, or as a set of bits.
_FEW_OTHERS = 32


class _Ids:
    """Components' ids, and the place of each, looked up as they are asked for."""

    def __init__(self, components: Sequence[tla.Component]) -> None:
        self._components = components
        self._places: dict[str, int] | None = None

    def of(self, place: int) -> str:
        return self._components[place].id

    def place(self, id_: object) -> int | None:
        if self._places is None:
            self._places = {c.id: place for place, c in enumerate(self._components)}
        return self._places.get(cast(str, id_))


class _InGroup(_AtOdds):
    """Those of `group`, the places, in order, of components that are at one time or
    one place, or that start first in a row, but the one at `place`."""

    def __init__(self, group: Sequence[int], place: int, ids: _Ids) -> None:
        self._group, self._place, self._ids = group, place, ids

    def _holds(self, place: int) -> bool:
        at = bisect.bisect_left(self._group, place)
        return at < len(self._group) and self._group[at] == place

    def __iter__(self) -> Iterator[str]:
        return (self._ids.of(other) for other in self._group if other != self._place)

    def __len__(self) -> int:
        return len(self._group) - self._holds(self._place)

    def __contains__(self, other: object) -> bool:
        place = self._ids.place(other)
        return place is not None and place != self._place and self._holds(place)


class _Crossing(_AtOdds):
    """The hierarchies the one at `place` crosses, at least one. They are found again
    each time, since to keep them would take a bit for each pair of hierarchies."""

    def __init__(self, place: int, crossings: _Crossings, ids: _Ids) -> None:
        self._place, self._crossings, self._ids = place, crossings, ids

    @property
    def _mask(self) -> int:
        return self._crossings.crossed_by(self._place)

    def __iter__(self) -> Iterator[str]:
        # The digits of an integer, in one go, are far quicker to read than its
        # bits one at a time, when all are read.
        digits = bin(self._mask)[:1:-1]
        return (
            self._ids.of(self._crossings.places[bit])
            for bit, digit in enumerate(digits)
            if digit == "1"
        )

    def __len__(self) -> int:
        return self._mask.bit_count()

    def _bit(self, other: object) -> int | None:
        place = self._ids.place(other)
        return None if place is None else self._crossings.bits.get(place)

    def __contains__(self, other: object) -> bool:
        bit = self._bit(other)
        return bit is not None and bool(self._mask >> bit & 1)

    def naming(self, limit: int, named: Collection[str]) -> tuple[list[str], int]:
        left = self._mask
        for other in named:
            bit = self._bit(other)
            if bit is not None:
                left &= ~(1 << bit)
        more = left.bit_count()
        kept = []
        while left and len(kept) < limit:
            lowest = left & -left
            kept.append(self._ids.of(self._crossings.places[lowest.bit_length() - 1]))
            left ^= lowest
        return kept, more - len(kept)


class _Crossings:
    """For each hierarchy of a timeline, those it crosses, as an integer with a bit
    for each hierarchy that can be crossed, the first's the lowest: what `_cross`
    says of two, said of one and all the others at once.

    `_cross` asks only how two hierarchies' starts, ends and levels compare. Put the
    times in order, and those that are `_lt` one of them, or that it is `_lt`, are
    all those before a point of the order, or from one on. The point is found by
    halving, with `_lt` itself, so a time that is close to another is found as
    `_cross` finds it (`_lt(a, b)` is false and then true as b goes up). So each
    thing `_cross` asks of a pair is, of one hierarchy and all the others, the set
    of those whose start, end or level comes before a point, which `_Below` gives,
    and its "and" and "not" are those of the sets.

    A hierarchy whose start, end or level can't be compared crosses none."""

    def __init__(self, components: Sequence[tla.Component]) -> None:
        hierarchies = [
            (place, component.attrs)
            for place, component in enumerate(components)
            if component.kind == "hierarchy"
            and all(
                _is_comparable(component.attrs.get(name))
                for name in ("start", "end", "level")
            )
        ]
        self.places = [place for place, _ in hierarchies]  # of each bit's hierarchy
        self.bits = {place: bit for bit, place in enumerate(self.places)}
        starts = [attrs["start"] for _, attrs in hierarchies]
        ends = [attrs["end"] for _, attrs in hierarchies]
        levels = [attrs["level"] for _, attrs in hierarchies]
        times = sorted({*starts, *ends})
        order = {time: rank for rank, time in enumerate(times)}
        # The first rank not before a time (its tolerance counts), and the first
        # that comes after it, for each time.
        self._before = [self._first_not_before(times, at) for at in range(len(times))]
        self._after = [self._first_after(times, at) for at in range(len(times))]
        self._start_ranks = [order[start] for start in starts]
        self._end_ranks = [order[end] for end in ends]
        ranked = {level: rank for rank, level in enumerate(sorted(set(levels)))}
        self._top_level = len(ranked) - 1
        self._level_ranks = [ranked[level] for level in levels]
        self._starts = _Below(self._start_ranks)
        self._ends = _Below(self._end_ranks)
        self._levels = _Below(self._level_ranks)

    @staticmethod
    def _first_not_before(times: Sequence[float], at: int) -> int:
        """The first rank whose time isn't `_lt` the one at `at`."""
        if not at or _lt(times[at - 1], times[at]):
            return at
        return bisect.bisect_left(
            times, True, 0, at, key=lambda time: not _lt(time, times[at])
        )

    @staticmethod
    def _first_after(times: Sequence[float], at: int) -> int:
        """The first rank whose time the one at `at` is `_lt`."""
        if at + 1 == len(times) or _lt(times[at], times[at + 1]):
            return at + 1
        return bisect.bisect_left(
            times, True, at + 1, len(times), key=lambda time: _lt(times[at], time)
        )

    def crossed_by(self, place: int) -> int:
        """The hierarchies that the one at `place`, which can be compared, crosses."""
        bit = self.bits[place]
        start, end = self._start_ranks[bit], self._end_ranks[bit]
        level = self._level_ranks[bit]
        crossed = self._starts.below(self._before[end]) & ~self._ends.below(
            self._after[start]
        )
        if level < self._top_level:  # those it lies inside, at a higher level
            crossed &= ~(
                self._starts.below(self._after[start])
                & ~self._ends.below(self._before[end])
                & ~self._levels.below(level + 1)
            )
        if level > 0:  # those that lie inside it, at a lower level
            crossed &= ~(
                ~self._starts.below(self._before[start])
                & self._ends.below(self._after[end])
                & self._levels.below(level)
            )
        return crossed & ~(1 << bit)


class _Below:
    """Which of some items have a rank below a number, as an integer with a bit for
    each item: the first of them, in the order of their ranks, a mark every few of
    them made in advance."""

    def __init__(self, ranks: Sequence[int]) -> None:
        self._items = sorted(range(len(ranks)), key=ranks.__getitem__)
        self._ranks = [ranks[item] for item in self._items]
        # More between marks for more of them, so that the marks don't take more
        # memory than a file of so many would.
        self._step = max(8, len(ranks) // 2048)
        self._marks = [0]
        mask = 0
        for done, item in enumerate(self._items, 1):
            mask |= 1 << item
            if done % self._step == 0:
                self._marks.append(mask)

    def below(self, rank: int) -> int:
        """The items whose rank is below `rank`."""
        count = bisect.bisect_left(self._ranks, rank)
        mark = count // self._step
        mask = self._marks[mark]
        for item in self._items[mark * self._step : count]:
            mask |= 1 << item
        return mask


class _Others:
    """The other components each component is checked with, found without
    comparing it with every one: those its rules could find it at odds with,
    among those added. Every component is added when reading, and each one kept
    so far when importing.

    When `every`, as in reading, all are added before any is checked, so nothing
    changes from one check to the next. Then only a few others of a group at odds
    are given to the rules, enough to say whether one is broken, and what
    `_Found.complete` gives their outcomes tells the rest."""

    def __init__(self, components: Sequence[tla.Component], every: bool) -> None:
        self._components = components
        self._every = every
        self._at_time = _ByValue()  # points' places, by kind and time
        # Hierarchies' places, by start, end and level, for those at the same
        # place as one with a start or an end that `==` finds equal to a number
        # but `_Spans` can't order with one: a bool, a Decimal, a complex.
        self._at_place = _ByValue()
        self._spans = _Spans(components)  # hierarchies, by the order of their starts
        self._rows = _ByValue()  # each row's ranges, as (start, place), by start
        self._ids = _Ids(components)
        self._following: dict[int, list[int]] = {}  # by the first that follows
        self._crossings: _Crossings | None = None

    def add(self, place: int) -> None:
        component = self._components[place]
        kind, attrs = component.kind, component.attrs
        if kind == "hierarchy":
            spot = (attrs.get("start"), attrs.get("end"), attrs.get("level"))
            self._at_place.at(spot).append(place)
            self._spans.add(place)
        elif kind == "range":
            start = attrs.get("start")
            if _is_number(start):  # what `_joined` compares
                bisect.insort(self._rows.at(attrs.get("row_id")), (start, place))
        elif kind in _POINT_KINDS:
            self._at_time.at((kind, attrs.get("time"))).append(place)

    def of(self, place: int) -> _Found:
        """The others the rules of the component at `place` could name, in the
        order given, found when a rule between components first reads them.

        A rule between components comes after the component's own rules, but
        for the point kinds: their time is compared with the others' as soon as
        it is a time within the media and their texts are text, before a
        harmony's or a key's values, or a PDF marker's page, are checked. The
        others are needed only from there, so one that breaks a rule of its own
        before it never looks for them.
        """
        return _Found(lambda: self._found(place))

    def _found(self, place: int) -> tuple[list[tla.Component], dict[str, _AtOdds]]:
        """Those given to the rules, and, by the code of the rule they break, the
        others of the groups they were chosen from."""
        component = self._components[place]
        kind, attrs = component.kind, component.attrs
        places: Iterable[int] = ()
        at_odds: dict[str, _AtOdds] = {}
        if kind == "hierarchy":
            places = self._hierarchies(place, attrs, at_odds)
        elif kind == "range":
            start = attrs.get("start")
            if attrs.get("joined_right") is not None and _is_number(start):
                places = self._next_ranges(attrs, start, at_odds)
        elif kind in _POINT_KINDS:
            time = attrs.get("time")
            if _is_number(time):
                group = self._at_time.get((kind, time))
                places = self._in_group(SAME_TIME, group, place, at_odds)
        others = [self._components[other] for other in sorted(places) if other != place]
        return others, at_odds

    def _in_group(
        self, code: str, group: Sequence[int], place: int, at_odds: dict[str, _AtOdds]
    ) -> Sequence[int]:
        """The places of `group`, to which the one at `place` belongs, that are
        given to the rule with the code `code`: all, or, when they are many, the
        first other, with the rest among `at_odds`."""
        if not self._every or len(group) - 1 <= _FEW_OTHERS:
            return group
        at_odds[code] = _InGroup(group, place, self._ids)
        return [next(other for other in group if other != place)]

    def _hierarchies(
        self, place: int, attrs: Mapping[str, Any], at_odds: dict[str, _AtOdds]
    ) -> Iterable[int]:
        start, end, level = attrs.get("start"), attrs.get("end"), attrs.get("level")
        if not (_is_number(start) and _is_number(end)):
            return ()
        group = self._at_place.get((start, end, level))
        places = set(self._in_group(SAME_PLACE, group, place, at_odds))
        if self._crossings is None:
            overlapping = self._spans.overlapping(
                start, end, _FEW_OTHERS if self._every else None
            )
            if overlapping is not None:
                places.update(overlapping)
                return places
            self._crossings = _Crossings(self._components)
        if _is_comparable(level):
            crossed = self._crossings.crossed_by(place)
            if crossed:
                first = (crossed & -crossed).bit_length() - 1
                places.add(self._crossings.places[first])
                at_odds[CROSSING] = _Crossing(place, self._crossings, self._ids)
        return places

    def _next_ranges(
        self, attrs: Mapping[str, Any], start: float, at_odds: dict[str, _AtOdds]
    ) -> Iterable[int]:
        """The ranges of the row that start first after `start`, which `_joined`
        could name: all, or, when they are many, the first and the one it joins, if
        it is one of them, with all of them among `at_odds`."""
        starts = self._rows.get(attrs.get("row_id"))
        first, stop = _next_starts(starts, start)
        if not self._every or stop - first <= _FEW_OTHERS:
            return [other for _, other in starts[first:stop]]
        head = starts[first][1]
        group = self._following.get(head)
        if group is None:
            group = self._following[head] = [other for _, other in starts[first:stop]]
        at_odds[BAD_JOIN] = in_group = _InGroup(group, -1, self._ids)
        joined = attrs["joined_right"]
        target = self._ids.place(joined) if isinstance(joined, str) else None
        if target is not None and joined in in_group:
            return {head, target}
        return {head}


class _Found:
    """The others a component is checked with, found the first time a rule
    between components reads them."""

    def __init__(
        self,
        find: Callable[[], tuple[list[tla.Component], dict[str, _AtOdds]]],
    ) -> None:
        self._find = find
        self._others: list[tla.Component] | None = None
        self._at_odds: dict[str, _AtOdds] = {}

    def __iter__(self) -> Iterator[tla.Component]:
        if self._others is None:
            self._others, self._at_odds = self._find()
        return iter(self._others)

    def complete(self, outcome: Outcome) -> Outcome:
        """`outcome` with all its others, where its rule was given only some."""
        at_odds = self._at_odds.get(outcome.code)
        if at_odds is None:
            return outcome
        return Outcome(outcome.ok, outcome.reason, at_odds, outcome.code, outcome.about)


class _ByValue:
    """Lists, each found by a value as `==` finds it: by its hash when it has one,
    else by comparing it with each value that has none."""

    def __init__(self) -> None:
        self._hashed: dict[Any, list[Any]] = {}
        self._unhashable: list[tuple[Any, list[Any]]] = []

    def at(self, value: Any) -> list[Any]:
        """The list for `value`, which is made, empty, the first time."""
        try:
            return self._hashed.setdefault(value, [])
        except TypeError:
            for other, items in self._unhashable:
                if other == value:
                    return items
            items: list[Any] = []
            self._unhashable.append((value, items))
            return items

    def get(self, value: Any) -> list[Any]:
        """What the lists for the values `==` finds equal to `value` hold, in
        order: not to be changed.

        A value with a hash is found by it, and is compared with each value that
        has none, which `==` can find equal to it: a frozenset and a set with
        the same members are. A value without one is compared with every value.
        Only a caller in Python can give one, since the reader refuses a value
        of the wrong type.
        """
        try:
            hashed = self._hashed.get(value)
        except TypeError:
            found = [items for other, items in self._hashed.items() if other == value]
        else:
            found = [] if hashed is None else [hashed]
        found += [items for other, items in self._unhashable if other == value]
        if len(found) == 1:
            return found[0]
        return sorted(itertools.chain.from_iterable(found))


class _Spans:
    """Hierarchies by the order of their starts, to find those added that overlap
    a span without looking at the others: a binary tree whose leaves follow the
    starts, each node holding the latest end among the hierarchies added below
    it. A hierarchy whose start or end can't be compared crosses none, and has no
    leaf."""

    def __init__(self, components: Sequence[tla.Component]) -> None:
        spans = sorted(
            (
                (component.attrs["start"], component.attrs["end"], place)
                for place, component in enumerate(components)
                if component.kind == "hierarchy"
                and _is_comparable(component.attrs.get("start"))
                and _is_comparable(component.attrs.get("end"))
            ),
            key=lambda span: span[0],
        )
        self._starts = [start for start, _, _ in spans]
        self._ends = [end for _, end, _ in spans]
        self._places = [place for _, _, place in spans]
        self._leaf_of = {place: leaf for leaf, place in enumerate(self._places)}
        self._leaves = 1 << max(len(spans) - 1, 0).bit_length()
        # Node 1 is the root, node n's children are 2n and 2n + 1, and the
        # leaves come last, in the starts' order.
        self._latest: list[float] = [-math.inf] * (2 * self._leaves)

    def add(self, place: int) -> None:
        leaf = self._leaf_of.get(place)
        if leaf is None:
            return
        end = self._ends[leaf]
        node = self._leaves + leaf
        while node and not self._latest[node] >= end:
            self._latest[node] = end
            node //= 2

    def overlapping(
        self, start: float, end: float, most: int | None = None
    ) -> list[int] | None:
        """The places of the hierarchies added that start before `end` and end
        after `start`: every one that a hierarchy from `start` to `end` crosses.
        None when there are more than `most`, as soon as that is known."""
        before = bisect.bisect_left(self._starts, end)
        found: list[int] = []
        nodes = [(1, 0, self._leaves)]
        while nodes:
            node, low, high = nodes.pop()
            if low >= before or not self._latest[node] > start:
                continue
            if node >= self._leaves:
                found.append(self._places[low])
                if most is not None and len(found) > most:
                    return None
                continue
            middle = (low + high) // 2
            nodes.append((2 * node + 1, middle, high))
            nodes.append((2 * node, low, middle))
        return found


def _next_starts(starts: Sequence[tuple[float, int]], start: float) -> tuple[int, int]:
    """Where, among a row's (start, place)s in order, are those of the ranges that
    start first after `start`: the index of the first and that after the last. They
    are every one `_joined` could name."""
    first = bisect.bisect_right(starts, (start, math.inf))
    if first == len(starts):
        return first, first
    return first, bisect.bisect_right(starts, (starts[first][0], math.inf), first)


def _qt_reads(text: str) -> bool:
    """Whether Qt reads `text` as a color, as `QColor(text).isValid()` says."""
    if text.startswith("#"):
        digits = text[1:]
        return len(digits) in _HEX_LENGTHS and all(c in _HEX_DIGITS for c in digits)
    # Qt reads a name of up to 255 UTF-16 units, in any case, leaving out spaces
    # and tabs. A NUL, or a character beyond Latin-1, ends it, and so does a lone
    # surrogate, which a file can hold (as "\ud83d"): it counts one unit.
    if len(text.encode("utf-16-le", "surrogatepass")) // 2 > 255:
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
    before its minutes are counted, so 59.96 is "01:00.0", not "00:60.0". A value
    too large for a float, which only a media length can be, is shown as it is."""
    if not _is_number(seconds):
        return _shown(seconds)
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
    of more than 4,300 digits unless set otherwise, is named instead, and so is a
    value holding one, by its type: "a list that can't be shown"."""
    try:
        return f"{value}"
    except ValueError:
        if isinstance(value, int):
            return "an integer too long to show"
        name = type(value).__name__
        article = "an" if name[:1].lower() in "aeiou" else "a"
        return f"{article} {name} that can't be shown"


def _broken(code: str, reason: str, about: str = "") -> Outcome:
    return Outcome(False, reason, code=code, about=about)


def _not_valid(attribute: str, value: Any) -> Outcome:
    return _broken(bad_code(attribute), not_valid(attribute, value))
