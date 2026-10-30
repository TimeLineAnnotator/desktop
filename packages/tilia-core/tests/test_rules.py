import collections
import copy
import importlib.util
import itertools
import math
import pickle
import random
import sys
import time
from decimal import Decimal
from fractions import Fraction
from importlib.metadata import metadata

import pytest
import webcolors

from tilia_core import rules, tla

OK = (True, "")
MEDIA = 60.0
PAGES = 3
ROW = "Ab12Cd"
ROWS = [{"id": ROW, "name": "Strings"}, {"id": "Ef34Gh", "name": "Winds"}]
INSTALL = 'pip install "tilia-core[harmony]"'

POINT_KINDS = ["marker", "harmony", "mode", "pdf_marker", "beat"]
POINT_NAMES = {
    "marker": "marker",
    "harmony": "harmony",
    "mode": "mode",
    "pdf_marker": "PDF page marker",
    "beat": "beat",
}
# Valid attributes for each kind, which a test changes one at a time.
VALID = {
    "marker": {"time": 1.0},
    "harmony": {"time": 1.0},
    "mode": {"time": 1.0},
    "pdf_marker": {"time": 1.0, "page_number": 1},
    "beat": {"time": 1.0},
    "hierarchy": {"start": 1.0, "end": 2.0, "level": 1},
    "range": {"start": 1.0, "end": 2.0, "row_id": ROW},
}


def check(kind, others=(), media_length=MEDIA, **attrs):
    """Checks a component of `kind` with VALID's attributes, changed by `attrs`."""
    if kind in ("harmony", "mode"):
        pytest.importorskip("music21", reason="needs the harmony extra")
    attrs = {**VALID[kind], **attrs}
    if kind == "pdf_marker":
        return rules.pdf_marker(media_length, others, attrs, page_count=PAGES)
    if kind == "range":
        return rules.range_(media_length, others, attrs, rows=ROWS)
    return getattr(rules, kind)(media_length, others, attrs)


def component(kind, **attrs):
    return tla.Component(id=tla.new_id(), kind=kind, attrs=attrs)


def hierarchy(start, end, level, **attrs):
    return component("hierarchy", start=start, end=end, level=level, **attrs)


def range_in(row_id, start, end, **attrs):
    return component("range", start=start, end=end, row_id=row_id, **attrs)


@pytest.fixture
def music21():
    return pytest.importorskip("music21", reason="needs the harmony extra")


@pytest.fixture
def default_int_digits():
    # Python's default limit on the digits of an integer it turns into text.
    if not hasattr(sys, "set_int_max_str_digits"):
        pytest.skip("this Python shows integers of any length")
    limit = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(4300)
    yield
    sys.set_int_max_str_digits(limit)


def uninstall_music21(patch):
    """Makes music21 look uninstalled, through `patch`: a monkeypatch, or one of
    its contexts."""
    find_spec = importlib.util.find_spec

    def find_spec_without_music21(name, *args, **kwargs):
        if name.partition(".")[0] == "music21":
            return None
        return find_spec(name, *args, **kwargs)

    patch.setattr(importlib.util, "find_spec", find_spec_without_music21)


@pytest.fixture
def without_music21(monkeypatch):
    uninstall_music21(monkeypatch)


@pytest.fixture
def broken_music21(monkeypatch):
    # Installed, so found, but importing it fails, as with a numpy it can't use.
    find_spec = importlib.util.find_spec

    def find_spec_with_music21(name, *args, **kwargs):
        if name.partition(".")[0] == "music21":
            return object()
        return find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec_with_music21)
    for name in ("music21", "music21.harmony", "music21.key"):
        monkeypatch.setitem(sys.modules, name, None)


@pytest.fixture
def music21_raising(tmp_path, monkeypatch):
    # A music21 that is installed but raises something other than ImportError
    # when imported, as with a numpy it can't use.
    package = tmp_path / "music21"
    package.mkdir()
    (package / "__init__.py").write_text(
        'raise AttributeError("np.float_ was removed in the NumPy 2.0 release.")\n'
    )
    for name in [name for name in sys.modules if name.partition(".")[0] == "music21"]:
        monkeypatch.delitem(sys.modules, name)
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()


# TiLiA's creation rules, which its importers apply: `validate_creation` of its
# point-like and segment-like components, and the range timeline's
# `_validate_component_creation`. They say whether TiLiA creates a component,
# for the tests that show a rule the core adds. They take only what TiLiA's
# creation rules look at: not a colour, a text or a harmony's values, which only
# `set_data` checks, so TiLiA's importers store any of them.


def tilia_creates_point(time, existing_times=(), media_length=MEDIA, **_):
    if time > media_length:
        return False
    elif time < 0:
        return False
    return time not in existing_times


def tilia_creates_hierarchy(start, end, level, existing=(), media_length=MEDIA, **_):
    if start > media_length:
        return False
    elif end > media_length:
        return False
    elif end <= start:
        return False
    return (start, end, level) not in existing


def tilia_creates_range(
    start, end, row_id, pre_start=None, post_end=None, media_length=MEDIA, **_
):
    if not row_id or row_id not in [row["id"] for row in ROWS]:
        return False
    if start >= end:
        return False
    if start < 0 or end > media_length:
        return False
    if pre_start is not None and pre_start < 0:
        return False
    if post_end is not None and post_end > media_length:
        return False
    return True


# `dev`'s comparisons of hierarchy boundaries since 2ceec157: two times count as
# the same when they are within 1e-9 of each other, or within a billionth of the
# larger, whichever is more (`math.isclose`'s default `rel_tol` is 1e-9).


def _times_close(a, b):
    return math.isclose(a, b, abs_tol=1e-9)


def _le(a, b):
    return a < b or _times_close(a, b)


def _lt(a, b):
    return a < b and not _times_close(a, b)


def tilia_boundary_conflicts(hierarchies):
    """`HierarchyTLComponentManager.get_boundary_conflicts`, on (start, end, level)s."""

    def starts_or_ends_strictly_inside(outer, inner):
        return (_lt(outer[0], inner[0]) and _lt(inner[0], outer[1])) or (
            _lt(outer[0], inner[1]) and _lt(inner[1], outer[1])
        )

    conflicts = []
    for hrc1, hrc2 in itertools.combinations(hierarchies, 2):
        start1, end1, level1 = hrc1
        start2, end2, level2 = hrc2
        if starts_or_ends_strictly_inside(hrc1, hrc2):
            if level2 >= level1:
                conflicts.append((hrc1, hrc2))
            elif not _lt(start2, start1) and _lt(end1, end2):
                conflicts.append((hrc1, hrc2))
        if starts_or_ends_strictly_inside(hrc2, hrc1):
            if level1 >= level2:
                conflicts.append((hrc2, hrc1))
            elif not _lt(start1, start2) and _lt(end2, end1):
                conflicts.append((hrc2, hrc1))
        if (
            _times_close(start1, start2)
            and _times_close(end1, end2)
            and level1 == level2
        ):
            conflicts.append((hrc1, hrc2))
    return conflicts


class TestOutcome:
    def test_a_kept_rule_is_true_and_no_reason(self):
        assert rules.OK == (True, "")
        assert rules.OK.others == ()

    def test_an_outcome_is_true_only_when_no_rule_is_broken(self):
        assert rules.OK
        assert not rules.Outcome(False, "Invalid row ID.")

    def test_its_truth_is_a_bool_whatever_ok_was_given_as(self):
        assert bool(rules.Outcome(1)) is True
        assert bool(rules.Outcome(0, "Invalid row ID.")) is False

    def test_ok_is_a_bool_however_its_read(self):
        assert rules.Outcome(1).ok is True
        ok, _ = rules.Outcome(0, "Invalid row ID.")
        assert ok is False

    def test_if_reads_as_keeping_to_the_rules(self):
        assert rules.marker(60.0, [], {"time": 1.0})
        assert not rules.marker(60.0, [], {"time": -1.0})
        assert not rules.hierarchy(60.0, [], {"start": 0.0, "end": 1.0, "level": 0})

    def test_a_broken_rule_unpacks_as_its_reason(self):
        ok, reason = rules.Outcome(False, "Invalid row ID.")

        assert (ok, reason) == (False, "Invalid row ID.")

    @pytest.mark.parametrize(
        "duplicate", [copy.copy, copy.deepcopy, lambda o: pickle.loads(pickle.dumps(o))]
    )
    def test_an_outcome_copies_and_pickles_whole(self, duplicate):
        outcome = rules.Outcome(False, "Invalid row ID.", ["a"])

        copied = duplicate(outcome)

        assert copied == (False, "Invalid row ID.")
        assert copied.others == ("a",)
        assert not copied
        assert duplicate(rules.OK)

    def test_cant_check_pickles_whole(self):
        error = rules.CantCheck("harmony")

        copied = pickle.loads(pickle.dumps(error))

        assert str(copied) == str(error)
        assert copied.kind == "harmony"

    def test_cant_check_copies_and_pickles_whatever_its_error(self):
        class Picky(Exception):
            def __init__(self, a, b):
                super().__init__(f"{a} {b}")

        error = rules.CantCheck("harmony", Picky(1, 2))

        for duplicate in (
            copy.copy,
            copy.deepcopy,
            lambda e: pickle.loads(pickle.dumps(e)),
        ):
            copied = duplicate(error)
            assert str(copied) == str(error)
            assert copied.kind == "harmony"

    def test_a_broken_rule_names_the_other_components(self):
        outcome = rules.Outcome(False, "Component would overlap", ["a", "b"])

        assert outcome == (False, "Component would overlap")
        assert outcome.others == ("a", "b")
        assert (outcome.ok, outcome.reason) == (False, "Component would overlap")

    @pytest.mark.parametrize(
        "outcome",
        [rules.Outcome(True), rules.Outcome(False, "Invalid row ID.", ["a"])],
    )
    def test_its_others_cant_be_changed(self, outcome):
        # Every outcome that keeps to the rules is the one `OK`, so changing its
        # others would change them all. The test changes new outcomes, so that it
        # leaves `OK` as it is if it fails.
        others = outcome.others

        with pytest.raises(AttributeError):
            outcome.others = ("zz",)

        assert outcome.others == others


class TestEveryKind:
    @pytest.mark.parametrize(
        "kind, attribute, reason",
        [
            ("marker", "time", "nan is not a valid time."),
            ("harmony", "time", "nan is not a valid time."),
            ("mode", "time", "nan is not a valid time."),
            ("pdf_marker", "time", "nan is not a valid time."),
            ("beat", "time", "nan is not a valid time."),
            ("hierarchy", "start", "nan is not a valid start."),
            ("hierarchy", "end", "nan is not a valid end."),
            ("hierarchy", "pre_start", "nan is not a valid pre start."),
            ("hierarchy", "post_end", "nan is not a valid post end."),
            ("range", "start", "nan is not a valid start."),
            ("range", "end", "nan is not a valid end."),
            ("range", "pre_start", "nan is not a valid pre start."),
            ("range", "post_end", "nan is not a valid post end."),
        ],
    )
    def test_a_time_of_nan(self, kind, attribute, reason):
        assert check(kind, **{attribute: float("nan")}) == (False, reason)

    def test_tilia_creates_components_at_nan(self):
        nan = float("nan")

        assert tilia_creates_point(nan)
        assert tilia_creates_hierarchy(nan, 2.0, 1)
        assert tilia_creates_hierarchy(1.0, nan, 1)
        assert tilia_creates_range(nan, 2.0, ROW)
        assert tilia_creates_range(1.0, 2.0, ROW, pre_start=nan)

    @pytest.mark.parametrize("value", [float("inf"), float("-inf"), "1.0", None, True])
    def test_a_time_that_isnt_a_finite_number(self, value):
        assert check("marker", time=value) == (
            False,
            f"{value} is not a valid time.",
        )

    def test_an_integer_too_large_for_a_float(self):
        huge = 10**400

        assert check("marker", time=huge) == (False, f"{huge} is not a valid time.")
        assert check("hierarchy", end=huge) == (False, f"{huge} is not a valid end.")

    @pytest.mark.parametrize("kind", [*POINT_KINDS, "hierarchy", "range"])
    def test_a_media_length_too_large_for_a_float(self, kind):
        assert check(kind, media_length=10**400) == OK

    def test_an_integer_too_long_to_show(self, default_int_digits):
        huge = 10**5000

        assert check("marker", time=huge) == (
            False,
            "an integer too long to show is not a valid time.",
        )
        assert check("hierarchy", level=-huge) == (
            False,
            "Level can't be below 1. Got 'an integer too long to show'",
        )

    @pytest.mark.parametrize(
        "value, shown",
        [
            ([10**5000], "a list"),
            ((10**5000,), "a tuple"),
            ({"a": 10**5000}, "a dict"),
            (collections.OrderedDict(a=10**5000), "an OrderedDict"),
        ],
    )
    def test_another_value_that_cant_be_shown(self, default_int_digits, value, shown):
        assert check("marker", label=value) == (
            False,
            f"{shown} that can't be shown is not a valid label.",
        )

    def test_a_missing_time(self):
        assert rules.marker(MEDIA, [], {}) == (False, "None is not a valid time.")

    @pytest.mark.parametrize("time", [0, 60])
    def test_times_given_as_integers(self, time):
        assert check("marker", time=time) == OK

    @pytest.mark.parametrize(
        "kind, attribute, reason",
        [
            ("marker", "label", "3 is not a valid label."),
            ("marker", "comments", "3 is not a valid comments."),
            ("hierarchy", "label", "3 is not a valid label."),
            ("range", "comments", "3 is not a valid comments."),
            ("harmony", "custom_text", "3 is not a valid custom text."),
            ("mode", "comments", "3 is not a valid comments."),
        ],
    )
    def test_a_text_that_isnt_text(self, kind, attribute, reason):
        assert check(kind, **{attribute: 3}) == (False, reason)

    @pytest.mark.parametrize("attribute", ["label", "comments"])
    def test_texts(self, attribute):
        assert check("marker", **{attribute: ""}) == OK
        assert check("marker", **{attribute: "Exposição 🎻"}) == OK

    def test_a_text_not_in_nfc_is_kept(self):
        # Text is stored in NFC by whatever stores it: the reader, the
        # writer and the CSV reader.
        assert check("marker", label="Exposição") == OK


class TestColor:
    def test_the_names_are_css_3s_and_transparent(self):
        # The names Qt reads: CSS 3's, from webcolors, and Qt's "transparent".
        for name in [*webcolors.names("css3"), "transparent"]:
            assert rules.color(name), name
        assert not rules.color("rebeccapurple")  # CSS 4's, which Qt doesn't read

    @pytest.mark.parametrize(
        "value",
        [
            None,
            "",
            "#f0a",
            "#FF00aa",
            "#80FF00aa",
            "#fff000aaa",
            "#ffff0000aaaa",
            "steelblue",
            "SteelBlue",
            "steel blue",
            "\tred ",
            "transparent",
        ],
    )
    def test_the_default_or_a_color_qt_reads(self, value):
        assert rules.color(value) == OK

    @pytest.mark.parametrize(
        "value",
        [
            "notacolor",
            "#ff",
            "#ffff",
            "#fffffffffffffff",
            "#ggg",
            "#１２３",
            " #fff",
            "rgb(1, 2, 3)",
            "red\n",
            "re\ud83d",
            0,
            True,
        ],
    )
    def test_a_color_that_isnt_one(self, value):
        assert rules.color(value) == (False, f"{value} is not a valid color.")

    def test_a_lone_surrogate_ends_a_name_as_another_character_beyond_latin_1(self):
        # A file can hold one, written as \ud83d. Qt reads a name up to it.
        assert rules.color("red\ud83d") == OK
        assert rules.color("\ud83dred") == (False, "\ud83dred is not a valid color.")
        assert rules.color(" " * 252 + "red\ud83d") == (
            False,
            " " * 252 + "red\ud83d is not a valid color.",
        )

    @pytest.mark.parametrize("kind", ["marker", "hierarchy", "range"])
    def test_each_kind_with_a_color_checks_it(self, kind):
        assert check(kind, color="#f0a") == OK
        assert check(kind, color="notacolor") == (
            False,
            "notacolor is not a valid color.",
        )

    @pytest.mark.parametrize(
        "kind, attrs, reason",
        [
            (
                "marker",
                {"time": 61.0},
                "Time '01:01.0' is bigger than media time '01:00.0'",
            ),
            ("hierarchy", {"level": 0}, "Level can't be below 1. Got '0'"),
            ("range", {"row_id": "Zz99Zz"}, "Invalid row ID."),
            ("marker", {"label": 3}, "3 is not a valid label."),
        ],
    )
    def test_a_bad_color_doesnt_hide_another_broken_rule(self, kind, attrs, reason):
        # An importer keeps a row whose color isn't one, so the color is checked last.
        assert check(kind, color="notacolor", **attrs) == (False, reason)

    def test_a_bad_row_color_doesnt_hide_another_broken_row(self):
        rows = [
            {"id": ROW, "name": "Strings", "color": "notacolor"},
            {"id": ROW, "name": "Winds"},
        ]

        assert rules.range_rows(rows) == (
            False,
            f"There is already a row with the id {ROW}.",
        )

    def test_colors_are_those_qt_reads(self):
        qt = pytest.importorskip("PySide6.QtGui", reason="compares with Qt")
        names = qt.QColor.colorNames()
        samples = [
            *names,
            *(name.upper() for name in names),
            *(" ".join(name) for name in names),
            "#fff",
            "#FfF",
            "#ffff",
            "#fffff",
            "#ff00ff00",
            "#fffffffff",
            "#ffffffffffff",
            "#fffffffffffffff",
            "#",
            "#+12345",
            "#12 345",
            "#\tfff",
            "#fff\t",
            " #fff",
            "fff",
            "red\t",
            "\tr\te\td\t",
            "red\n",
            "red ",
            "red\x00",
            "re\x00d",
            "redΩ",
            "redΩblah",
            "Khaki",
            "whİte",
            "ſteelblue",
            "ＲＥＤ",
            "red\U0001f3bb",
            "re\ud83d",
            "red\ud83d",
            "\ud83dred",
            "red\udfbb",
            " " * 251 + "red\ud83d",
            " " * 252 + "red\ud83d",
            "notacolor",
            "a" * 300,
            " " * 300 + "red",
            " " * 250 + "red",
        ]

        disagree = [
            sample
            for sample in samples
            if rules.color(sample).ok is not qt.QColor(sample).isValid()
        ]

        assert disagree == []


class TestPointKinds:
    @pytest.mark.parametrize("kind", POINT_KINDS)
    @pytest.mark.parametrize("time", [0.0, 30.0, MEDIA])
    def test_a_time_from_0_to_the_media_length(self, kind, time):
        assert check(kind, time=time) == OK

    @pytest.mark.parametrize("kind", POINT_KINDS)
    def test_a_negative_time(self, kind):
        assert check(kind, time=-1.0) == (
            False,
            "Time can't be negative. Got '-00:01.0'",
        )

    @pytest.mark.parametrize(
        "time, shown",
        [(-0.5, "-00:00.5"), (-61.5, "-01:01.5"), (-3725.0, "-1:02:05.0")],
    )
    def test_a_negative_time_is_shown_with_a_minus_sign(self, time, shown):
        assert check("marker", time=time, media_length=7200.0) == (
            False,
            f"Time can't be negative. Got '{shown}'",
        )

    @pytest.mark.parametrize("kind", POINT_KINDS)
    def test_a_time_beyond_the_media_length(self, kind):
        assert check(kind, time=60.5) == (
            False,
            "Time '01:00.5' is bigger than media time '01:00.0'",
        )

    def test_times_of_an_hour_or_more_show_hours(self):
        assert check("marker", time=3725.0, media_length=3600.0) == (
            False,
            "Time '1:02:05.0' is bigger than media time '1:00:00.0'",
        )

    def test_media_length_given_as_an_integer(self):
        assert check("marker", time=61.0, media_length=60) == (
            False,
            "Time '01:01.0' is bigger than media time '01:00.0'",
        )

    @pytest.mark.parametrize(
        "media_length, shown",
        [(59.96, "01:00.0"), (3599.96, "1:00:00.0"), (59.94, "00:59.9")],
    )
    def test_a_time_is_rounded_before_its_minutes_are_counted(
        self, media_length, shown
    ):
        assert check("marker", time=7200.0, media_length=media_length) == (
            False,
            f"Time '2:00:00.0' is bigger than media time '{shown}'",
        )

    @pytest.mark.parametrize("kind", POINT_KINDS)
    @pytest.mark.parametrize("time", [0.0, 1.0, MEDIA])
    def test_a_time_another_component_of_the_kind_has(self, kind, time):
        same = component(kind, **{**VALID[kind], "time": time})
        others = [component(kind, **{**VALID[kind], "time": 30.5}), same]

        outcome = check(kind, others, time=time)

        assert outcome == (
            False,
            f"There is already a {POINT_NAMES[kind]} component at the selected position.",
        )
        assert outcome.others == (same.id,)

    @pytest.mark.parametrize("kind", POINT_KINDS)
    def test_another_kind_at_the_same_time(self, kind):
        other_kind = "mode" if kind == "harmony" else "harmony"
        others = [component(other_kind, time=1.0)]

        assert check(kind, others, time=1.0) == OK

    def test_bounds_are_checked_before_other_components(self):
        others = [component("marker", time=61.0)]

        assert check("marker", others, time=61.0) == (
            False,
            "Time '01:01.0' is bigger than media time '01:00.0'",
        )


class TestPdfMarker:
    @pytest.mark.parametrize("page_number", [1, 2, PAGES])
    def test_a_page_the_pdf_has(self, page_number):
        assert check("pdf_marker", page_number=page_number) == OK

    @pytest.mark.parametrize("page_number", [0, PAGES + 1, -1])
    def test_a_page_the_pdf_doesnt_have(self, page_number):
        assert check("pdf_marker", page_number=page_number) == (
            False,
            "The PDF has no page with that number.",
        )

    def test_a_pdf_that_cant_be_read_has_no_pages(self):
        attrs = {"time": 1.0, "page_number": 1}

        assert rules.pdf_marker(MEDIA, [], attrs, page_count=0) == (
            False,
            "The PDF has no page with that number.",
        )

    @pytest.mark.parametrize("page_number", [1.5, 1.0, "1", True, None])
    def test_a_page_number_that_isnt_an_integer(self, page_number):
        assert check("pdf_marker", page_number=page_number) == (
            False,
            f"{page_number} is not a valid page number.",
        )


class TestHarmony:
    @pytest.mark.parametrize(
        "attribute, values",
        [
            ("step", [0, 6]),
            ("applied_to", [0, 6]),
            ("accidental", [-2, -1, 0, 1, 2]),
            ("inversion", [0, 2]),
            ("level", [1, 2]),
            ("display_mode", ["letter", "roman", "custom"]),
            ("custom_text_font_type", ["analytic", "normal"]),
        ],
    )
    def test_values_tilia_allows(self, attribute, values):
        for value in values:
            assert check("harmony", **{attribute: value}) == OK

    @pytest.mark.parametrize(
        "attribute, value, reason",
        [
            ("step", -1, "-1 is not a valid step."),
            ("step", 7, "7 is not a valid step."),
            ("step", 1.0, "1.0 is not a valid step."),
            ("step", True, "True is not a valid step."),
            ("applied_to", 7, "7 is not a valid applied to."),
            ("accidental", 3, "3 is not a valid accidental."),
            ("accidental", -3, "-3 is not a valid accidental."),
            ("quality", "maj", "maj is not a valid quality."),
            ("quality", None, "None is not a valid quality."),
            ("inversion", -1, "-1 is not a valid inversion."),
            ("inversion", 3, "3 is not a valid inversion."),
            ("level", 0, "0 is not a valid level."),
            ("level", 3, "3 is not a valid level."),
            ("display_mode", "roman2", "roman2 is not a valid display mode."),
            (
                "custom_text_font_type",
                "bold",
                "bold is not a valid custom text font type.",
            ),
        ],
    )
    def test_values_tilia_refuses_when_it_sets_them(self, attribute, value, reason):
        assert check("harmony", **{attribute: value}) == (False, reason)

    def test_every_quality_music21_has(self, music21):
        for quality in music21.harmony.CHORD_TYPES:
            assert check("harmony", quality=quality) == OK

    def test_qualities_are_read_from_the_installed_music21(self, music21, monkeypatch):
        monkeypatch.setitem(
            music21.harmony.CHORD_TYPES, "made-up", ["1,2,3,4", ["made-up"]]
        )

        assert check("harmony", quality="made-up", inversion=3) == OK

    @pytest.mark.parametrize(
        "quality, inversions",
        [("major", 2), ("dominant-seventh", 3), ("power", 0), ("Italian", 0)],
    )
    def test_inversions_as_tilia_counts_them(self, quality, inversions):
        assert check("harmony", quality=quality, inversion=inversions) == OK
        assert check("harmony", quality=quality, inversion=inversions + 1) == (
            False,
            f"{inversions + 1} is not a valid inversion.",
        )

    @pytest.mark.parametrize(
        "quality, base, tone, inversions",
        [
            ("dominant-seventh-flat-ninth", "dominant-seventh", "b9", 3),
            ("dominant-seventh-sharp-ninth", "dominant-seventh", "#9", 3),
            ("dominant-seventh-sharp-eleventh", "dominant-seventh", "#11", 3),
            ("dominant-seventh-flat-thirteenth", "dominant-seventh", "b13", 3),
            ("dominant-seventh-added-thirteenth", "dominant-seventh", "13", 3),
            ("dominant-ninth-sharp-eleventh", "dominant-ninth", "#11", 4),
            ("major-seventh-sharp-eleventh", "major-seventh", "#11", 3),
            ("major-seventh-added-sixth", "major-seventh", "6", 3),
            ("major-sixth-added-ninth", "major-sixth", "9", 3),
            ("minor-sixth-added-ninth", "minor-sixth", "9", 3),
            ("major-added-ninth", "major", "9", 2),
            ("minor-added-ninth", "minor", "9", 2),
            ("minor-seventh-added-eleventh", "minor-seventh", "11", 3),
        ],
    )
    def test_the_added_tone_qualities_tilia_has(self, quality, base, tone, inversions):
        # An added tone isn't one the chord can be inverted to: the base quality's
        # inversions count.
        assert rules.split_added_tone(quality) == (base, tone)
        assert check("harmony", quality=quality, inversion=inversions) == OK
        assert check("harmony", quality=quality, inversion=inversions + 1) == (
            False,
            f"{inversions + 1} is not a valid inversion.",
        )

    def test_a_quality_without_an_added_tone_is_its_own_base(self):
        assert rules.split_added_tone("major") == ("major", "")

    def test_the_inversion_of_the_default_quality(self):
        assert check("harmony", inversion=2) == OK

    def test_the_rules_in_order(self):
        assert check("harmony", step=7, level=3) == (False, "7 is not a valid step.")


class TestMode:
    @pytest.mark.parametrize(
        "attribute, values",
        [
            ("step", [0, 6]),
            ("accidental", [-2, 2]),
            (
                "type",
                [
                    "major",
                    "minor",
                    "dorian",
                    "phrygian",
                    "lydian",
                    "mixolydian",
                    "locrian",
                ],
            ),
            ("level", [1, 2]),
        ],
    )
    def test_values_tilia_allows(self, attribute, values):
        for value in values:
            assert check("mode", **{attribute: value}) == OK

    @pytest.mark.parametrize(
        "attribute, value, reason",
        [
            ("step", 7, "7 is not a valid step."),
            ("accidental", 3, "3 is not a valid accidental."),
            ("type", "ionian", "ionian is not a valid type."),
            ("type", "aeolian", "aeolian is not a valid type."),
            ("type", "dorianx", "dorianx is not a valid type."),
            ("level", 3, "3 is not a valid level."),
        ],
    )
    def test_values_tilia_refuses_when_it_sets_them(self, attribute, value, reason):
        assert check("mode", **{attribute: value}) == (False, reason)

    def test_types_are_read_from_the_installed_music21(self, music21, monkeypatch):
        monkeypatch.setitem(music21.key.modeSharpsAlter, "made-up", 0)

        assert check("mode", type="made-up") == OK


class TestWithoutMusic21:
    @pytest.mark.parametrize("kind", ["harmony", "mode"])
    def test_checking_fails_naming_the_install_command(self, kind, without_music21):
        with pytest.raises(rules.CantCheck) as raised:
            getattr(rules, kind)(MEDIA, [], {"time": 1.0})

        assert INSTALL in str(raised.value)
        assert raised.value.command == INSTALL

    def test_the_command_installs_an_extra_the_core_has(self):
        assert "harmony" in metadata("tilia-core").get_all("Provides-Extra", [])

    @pytest.mark.parametrize("kind", ["harmony", "mode"])
    def test_a_music21_that_wont_import(self, kind, broken_music21):
        with pytest.raises(rules.CantCheck) as raised:
            getattr(rules, kind)(MEDIA, [], {"time": 1.0})

        assert isinstance(raised.value.__cause__, ImportError)
        assert str(raised.value) == (
            f"checking a {kind} needs music21, which can't be imported"
            " (ModuleNotFoundError: import of music21.harmony halted; None in"
            f" sys.modules): {INSTALL}"
        )

    @pytest.mark.parametrize("kind", ["harmony", "mode"])
    def test_a_bad_color_doesnt_hide_that_it_cant_be_checked(
        self, kind, without_music21
    ):
        # An importer keeps a component whose only problem is its color.
        with pytest.raises(rules.CantCheck):
            getattr(rules, kind)(MEDIA, [], {"time": 1.0, "color": "notacolor"})

    @pytest.mark.parametrize("kind", ["harmony", "mode"])
    def test_a_music21_that_raises_something_else(self, kind, music21_raising):
        with pytest.raises(rules.CantCheck) as raised:
            getattr(rules, kind)(MEDIA, [], {"time": 1.0})

        assert isinstance(raised.value.__cause__, AttributeError)
        assert str(raised.value) == (
            f"checking a {kind} needs music21, which can't be imported"
            " (AttributeError: np.float_ was removed in the NumPy 2.0 release.):"
            f" {INSTALL}"
        )

    @pytest.mark.parametrize("kind", ["harmony", "mode"])
    def test_the_other_rules_are_checked(self, kind, without_music21):
        attrs = {"time": 1.0, "level": 3, "quality": "maj", "type": "dorianx"}

        assert getattr(rules, kind)(MEDIA, [], attrs) == (
            False,
            "3 is not a valid level.",
        )

    @pytest.mark.parametrize("kind", ["marker", "pdf_marker", "beat", "hierarchy"])
    def test_other_kinds_dont_need_it(self, kind, without_music21):
        assert check(kind) == OK


class TestHierarchy:
    @pytest.mark.parametrize("start, end", [(0.0, 1.0), (1.0, MEDIA), (0.0, MEDIA)])
    def test_within_the_media_length(self, start, end):
        assert check("hierarchy", start=start, end=end) == OK

    def test_a_start_beyond_the_media_length(self):
        assert check("hierarchy", start=61.0, end=62.0) == (
            False,
            "Start time '61.0' is bigger than media time '60.0'",
        )

    def test_an_end_beyond_the_media_length(self):
        assert check("hierarchy", start=1.0, end=61.0) == (
            False,
            "End time '61.0' is bigger than media time '60.0'",
        )

    @pytest.mark.parametrize("start", [-1.0, -0.5])
    def test_a_negative_start(self, start):
        assert check("hierarchy", start=start) == (
            False,
            f"Start time can't be negative. Got '{start}'",
        )
        assert tilia_creates_hierarchy(start, 2.0, 1)

    @pytest.mark.parametrize("end", [2.0, 1.0])
    def test_an_end_not_after_its_start(self, end):
        assert check("hierarchy", start=2.0, end=end) == (
            False,
            f"End time '{end}' should be bigger than start time '2.0'",
        )

    @pytest.mark.parametrize(
        "start, end, reason",
        [
            (61, 62, "Start time '61.0' is bigger than media time '60.0'"),
            (1, 61, "End time '61.0' is bigger than media time '60.0'"),
            (-1, 2, "Start time can't be negative. Got '-1.0'"),
            (2, 1, "End time '1.0' should be bigger than start time '2.0'"),
        ],
    )
    def test_numbers_given_as_integers_read_as_tilias_floats(self, start, end, reason):
        assert check("hierarchy", start=start, end=end, media_length=60) == (
            False,
            reason,
        )

    @pytest.mark.parametrize("level", [0, -1])
    def test_a_level_below_1(self, level):
        assert check("hierarchy", level=level) == (
            False,
            f"Level can't be below 1. Got '{level}'",
        )
        assert tilia_creates_hierarchy(1.0, 2.0, level)

    @pytest.mark.parametrize("level", [1.5, 1.0, "1", True, None])
    def test_a_level_that_isnt_an_integer(self, level):
        assert check("hierarchy", level=level) == (
            False,
            f"{level} is not a valid level.",
        )

    @pytest.mark.parametrize("pre_start", [None, 0.0, 0.5, 1.0])
    def test_a_pre_start_from_0_to_the_start(self, pre_start):
        assert check("hierarchy", pre_start=pre_start) == OK

    def test_a_pre_start_below_0(self):
        assert check("hierarchy", pre_start=-0.5) == (
            False,
            "pre_start is outside media bounds.",
        )
        assert tilia_creates_hierarchy(1.0, 2.0, 1, pre_start=-0.5)

    def test_a_pre_start_after_the_start(self):
        assert check("hierarchy", pre_start=1.5) == (
            False,
            "pre_start can't be after start time.",
        )
        assert tilia_creates_hierarchy(1.0, 2.0, 1, pre_start=1.5)

    @pytest.mark.parametrize("post_end", [None, 2.0, 30.0, MEDIA])
    def test_a_post_end_from_the_end_to_the_media_length(self, post_end):
        assert check("hierarchy", post_end=post_end) == OK

    def test_a_post_end_before_the_end(self):
        assert check("hierarchy", post_end=1.5) == (
            False,
            "post_end can't be before end time.",
        )
        assert tilia_creates_hierarchy(1.0, 2.0, 1, post_end=1.5)

    def test_a_post_end_beyond_the_media_length(self):
        assert check("hierarchy", post_end=60.5) == (
            False,
            "post_end is outside media bounds.",
        )
        assert tilia_creates_hierarchy(1.0, 2.0, 1, post_end=60.5)

    def test_the_position_of_another_hierarchy(self):
        same = hierarchy(1.0, 2.0, 1)
        others = [hierarchy(0.0, 1.0, 1), same]

        outcome = check("hierarchy", others, start=1.0, end=2.0, level=1)

        assert outcome == (
            False,
            "There is already a hierarchy component at the selected position.",
        )
        assert outcome.others == (same.id,)

    def test_the_same_times_at_another_level(self):
        others = [hierarchy(1.0, 2.0, 1)]

        assert check("hierarchy", others, start=1.0, end=2.0, level=2) == OK

    def test_times_are_checked_before_other_components(self):
        others = [hierarchy(2.0, 1.0, 1)]

        assert check("hierarchy", others, start=2.0, end=1.0) == (
            False,
            "End time '1.0' should be bigger than start time '2.0'",
        )

    @pytest.mark.parametrize(
        "existing, candidate",
        [
            ((0, 10, 1), (5, 15, 1)),  # they cross, at one level
            ((5, 15, 1), (0, 10, 1)),
            ((0, 10, 2), (5, 15, 1)),  # they cross, at two levels
            ((0, 10, 1), (5, 15, 2)),
            ((0, 10, 1), (2, 5, 2)),  # inside a lower one
            ((0, 10, 1), (0, 5, 2)),
            ((2, 5, 1), (0, 10, 1)),  # around one at its level
            ((2, 5, 2), (0, 10, 1)),  # around a higher one
            ((0, 10, 1), (2, 5, 1)),  # inside one at its level
        ],
    )
    def test_hierarchies_that_dont_nest(self, existing, candidate):
        other = hierarchy(*existing)
        start, end, level = candidate

        outcome = check("hierarchy", [other], start=start, end=end, level=level)

        assert outcome == (False, "Component would overlap with existing component.")
        assert outcome.others == (other.id,)
        assert tilia_creates_hierarchy(*candidate, existing=[existing])

    @pytest.mark.parametrize(
        "existing, candidate",
        [
            ((0, 10, 2), (2, 5, 1)),  # inside a higher one
            ((0, 10, 2), (0, 10, 1)),  # the same times, at another level
            ((2, 5, 1), (0, 10, 2)),  # around a lower one
            ((0, 10, 1), (10, 20, 1)),  # side by side
            ((10, 20, 1), (0, 10, 2)),
        ],
    )
    def test_hierarchies_that_nest(self, existing, candidate):
        start, end, level = candidate
        others = [hierarchy(*existing)]

        assert check("hierarchy", others, start=start, end=end, level=level) == OK

    def test_every_hierarchy_it_crosses(self):
        crossed = [hierarchy(0, 10, 1), hierarchy(10, 20, 1)]
        others = [*crossed, hierarchy(0, 30, 3)]

        outcome = check("hierarchy", others, start=5, end=15, level=2)

        assert outcome.others == tuple(h.id for h in crossed)

    def test_crossing_one_whose_start_is_a_huge_integer(self):
        other = hierarchy(-(10**400), 10, 1)

        outcome = check("hierarchy", [other], start=5, end=15, level=1)

        assert outcome == (False, "Component would overlap with existing component.")

    def test_crossing_one_whose_level_is_a_huge_integer(self):
        other = hierarchy(0, 10, 10**400)

        outcome = check("hierarchy", [other], start=5, end=15, level=1)

        assert outcome == (False, "Component would overlap with existing component.")

    def test_crossing_one_whose_level_is_written_as_a_float(self):
        other = hierarchy(0, 10, 1.0)

        outcome = check("hierarchy", [other], start=5, end=15, level=1)

        assert outcome == (False, "Component would overlap with existing component.")

    def test_nesting_is_tilias_boundary_conflicts(self):
        # Every pair of hierarchies with times from 0 to 4 and levels from 1 to 8.
        spans = [
            (start, end, level)
            for start, end in itertools.combinations(range(5), 2)
            for level in range(1, 9)
        ]
        for existing, candidate in itertools.product(spans, repeat=2):
            start, end, level = candidate
            others = [hierarchy(*existing)]

            outcome = check("hierarchy", others, start=start, end=end, level=level)

            conflicts = tilia_boundary_conflicts([existing, candidate])
            assert outcome.ok is not bool(conflicts), (existing, candidate)

    @pytest.mark.parametrize(
        "existing, candidate",
        [
            # As in files TiLiA saved before it rescaled subtrees in one step.
            ((0.0, 1.0, 1), (1.0 - 1e-13, 2.0, 1)),
            # Below 1 s, boundaries within 1e-9 meet.
            ((1e-13, 1.0, 2), (0.0, 1.0, 1)),
            ((0.0, 0.5, 1), (0.5 - 9e-10, 1.0, 1)),
            # Above it, boundaries within a billionth of the larger.
            ((0.0, 3600.0, 1), (3600.0 - 2e-6, 3601.0, 1)),
        ],
    )
    def test_close_boundaries_meet(self, existing, candidate):
        start, end, level = candidate
        others = [hierarchy(*existing)]

        outcome = check(
            "hierarchy", others, media_length=7200.0, start=start, end=end, level=level
        )

        assert outcome == OK

    @pytest.mark.parametrize(
        "existing, candidate",
        [
            ((0.0, 0.5, 1), (0.5 - 2e-9, 1.0, 1)),
            ((0.0, 3600.0, 1), (3600.0 - 5e-6, 3601.0, 1)),
        ],
    )
    def test_boundaries_further_apart_cross(self, existing, candidate):
        start, end, level = candidate
        others = [hierarchy(*existing)]

        outcome = check(
            "hierarchy", others, media_length=7200.0, start=start, end=end, level=level
        )

        assert outcome == (False, "Component would overlap with existing component.")

    def test_nesting_with_float_noise_is_tilias_boundary_conflicts(self):
        # Every pair of spans with boundaries from 0 to 4 s at levels 1 to 3, with
        # each boundary moved by up to 2e-9, and none before 0. Below 1 s, 1e-9 is
        # more than a billionth of a time, and above it less, so the sweep compares
        # both parts of the tolerance.
        noise = random.Random(2026)
        moves = (0, 1e-13, -1e-13, 5e-10, -5e-10, 2e-9, -2e-9)
        spans = [
            (start, end, level)
            for start, end in itertools.combinations((0.0, 0.25, 0.5, 1.0, 2.0, 4.0), 2)
            for level in (1, 2, 3)
        ]
        for existing, candidate in itertools.product(spans, repeat=2):
            for _ in range(4):
                moved = [
                    (
                        max(0.0, start + noise.choice(moves)),
                        end + noise.choice(moves),
                        level,
                    )
                    for start, end, level in (existing, candidate)
                ]
                start, end, level = moved[1]

                outcome = check(
                    "hierarchy",
                    [hierarchy(*moved[0])],
                    start=start,
                    end=end,
                    level=level,
                )

                conflicts = tilia_boundary_conflicts(moved)
                assert outcome.ok is not bool(conflicts), moved

    def test_other_kinds_arent_compared(self):
        others = [component("marker", time=1.0), range_in(ROW, 0.0, 5.0)]

        assert check("hierarchy", others) == OK


class TestRange:
    def test_a_range_in_a_row(self):
        assert check("range") == OK

    @pytest.mark.parametrize(
        "start, end, pre_start, post_end",
        [
            (0.0, MEDIA, None, None),
            (1.0, 2.0, 0.0, MEDIA),
            (1.0, 2.0, 1.0, 2.0),
            (0.0, MEDIA, 0.0, MEDIA),
        ],
    )
    def test_the_edges(self, start, end, pre_start, post_end):
        attrs = {"start": start, "end": end, "pre_start": pre_start}

        assert check("range", **attrs, post_end=post_end) == OK

    @pytest.mark.parametrize("row_id", ["", None, "Zz99Zz"])
    def test_a_row_the_timeline_doesnt_have(self, row_id):
        assert check("range", row_id=row_id) == (False, "Invalid row ID.")

    @pytest.mark.parametrize("end", [1.0, 0.5])
    def test_an_end_not_after_its_start(self, end):
        assert check("range", start=1.0, end=end) == (
            False,
            "Start time must be before end time.",
        )

    @pytest.mark.parametrize("start, end", [(-0.5, 2.0), (1.0, 60.5)])
    def test_outside_the_media(self, start, end):
        assert check("range", start=start, end=end) == (
            False,
            "Range is outside media bounds.",
        )

    def test_a_pre_start_below_0(self):
        assert check("range", pre_start=-0.5) == (
            False,
            "pre_start is outside media bounds.",
        )

    def test_a_pre_start_after_the_start(self):
        assert check("range", pre_start=1.5) == (
            False,
            "pre_start can't be after start time.",
        )
        assert tilia_creates_range(1.0, 2.0, ROW, pre_start=1.5)

    def test_a_post_end_beyond_the_media_length(self):
        assert check("range", post_end=60.5) == (
            False,
            "post_end is outside media bounds.",
        )

    def test_a_post_end_before_the_end(self):
        assert check("range", post_end=1.5) == (
            False,
            "post_end can't be before end time.",
        )
        assert tilia_creates_range(1.0, 2.0, ROW, post_end=1.5)

    def test_the_row_is_checked_first(self):
        assert check("range", start=2.0, end=1.0, row_id="Zz99Zz") == (
            False,
            "Invalid row ID.",
        )

    def test_ranges_in_a_row_may_overlap(self):
        others = [range_in(ROW, 0.0, 5.0), range_in(ROW, 1.0, 2.0)]

        assert check("range", others, start=1.0, end=2.0) == OK


class TestJoinedRight:
    def test_joined_to_the_next_range_in_its_row(self):
        following = range_in(ROW, 2.0, 3.0)
        others = [range_in(ROW, 0.0, 1.0), range_in(ROW, 4.0, 5.0), following]

        assert check("range", others, joined_right=following.id) == OK

    def test_the_next_ranges_share_their_start(self):
        following = [range_in(ROW, 2.0, 3.0), range_in(ROW, 2.0, 4.0)]

        for joined in following:
            assert check("range", following, joined_right=joined.id) == OK

    def test_a_range_with_the_same_start_doesnt_come_next(self):
        following = range_in(ROW, 2.0, 3.0)
        others = [range_in(ROW, 1.0, 1.5), following]

        assert check("range", others, joined_right=following.id) == OK

    def test_the_last_range_of_its_row(self):
        others = [range_in(ROW, 0.0, 1.0), range_in("Ef34Gh", 2.0, 3.0)]

        assert check("range", others, joined_right=others[1].id) == (
            False,
            "joined_with_next=true on last range of row 'Strings';"
            " no next neighbor to join with",
        )

    def test_the_next_range_doesnt_start_at_its_end(self):
        following = range_in(ROW, 2.5, 3.0)
        others = [following, range_in(ROW, 4.0, 5.0)]

        outcome = check("range", others, joined_right=following.id)

        assert outcome == (
            False,
            "joined_with_next=true but next range on row 'Strings' starts at 2.5"
            " (must equal 2.0 for ranges to join)",
        )
        assert outcome.others == (following.id,)

    def test_joined_to_a_range_that_isnt_the_next(self):
        between = range_in(ROW, 1.5, 1.8)
        later = range_in(ROW, 2.0, 3.0)

        outcome = check("range", [between, later], end=1.5, joined_right=later.id)

        assert outcome == (
            False,
            "joined_with_next=true but the range it joins isn't the next range"
            " on row 'Strings'",
        )
        assert outcome.others == (between.id,)

    def test_joined_to_a_range_in_another_row(self):
        following = range_in(ROW, 2.0, 3.0)
        elsewhere = range_in("Ef34Gh", 2.0, 3.0)

        outcome = check("range", [following, elsewhere], joined_right=elsewhere.id)

        assert outcome == (
            False,
            "joined_with_next=true but the range it joins isn't the next range"
            " on row 'Strings'",
        )


class TestRows:
    def test_rows(self):
        assert rules.range_rows(ROWS) == OK
        assert rules.range_rows([{"id": "000000", "name": "", "color": "#f0a"}]) == OK

    @pytest.mark.parametrize(
        "row_id", ["Ab12C", "Ab12Cd7", "Ab-2Cd", "Ab12Cé", 123456, None]
    )
    def test_an_id_that_isnt_six_letters_and_digits(self, row_id):
        assert rules.range_rows([{"id": row_id, "name": "Strings"}]) == (
            False,
            f"{row_id} is not a valid row id.",
        )

    def test_an_id_two_rows_have(self):
        rows = [{"id": ROW, "name": "Strings"}, {"id": ROW, "name": "Winds"}]

        assert rules.range_rows(rows) == (
            False,
            f"There is already a row with the id {ROW}.",
        )

    @pytest.mark.parametrize("name", [3, None])
    def test_a_name_that_isnt_text(self, name):
        assert rules.range_rows([{"id": ROW, "name": name}]) == (
            False,
            f"{name} is not a valid row name.",
        )

    @pytest.mark.parametrize("color", [None, "", "steelblue"])
    def test_a_color(self, color):
        assert rules.range_rows([{"id": ROW, "name": "Strings", "color": color}]) == OK

    def test_a_color_that_isnt_one(self):
        assert rules.range_rows(
            [{"id": ROW, "name": "Strings", "color": "notacolor"}]
        ) == (
            False,
            "notacolor is not a valid color.",
        )


class TestNotValid:
    @pytest.mark.parametrize(
        "attribute, value, text",
        [
            ("time", "abc", "abc is not a valid time."),
            ("post_end", "abc", "abc is not a valid post end."),
            ("label", 3, "3 is not a valid label."),
            ("page_number", 1.5, "1.5 is not a valid page number."),
            (
                "custom_text_font_type",
                "bold",
                "bold is not a valid custom text font type.",
            ),
        ],
    )
    def test_one_text_for_a_value_that_isnt_one(self, attribute, value, text):
        assert rules.not_valid(attribute, value) == text


# A whole timeline at once: check_timeline gives each component what its kind's
# function gives, with the others as an import or a reading sees them.

MISSING = object()  # a key the component doesn't have
NAN = float("nan")
ODD_NUMBERS = [NAN, float("inf"), "1.0", None, True, 10**400, -(10**400), [1.0]]
TEXTS = ([MISSING, MISSING, "", "Exposição"], [3])
COLORS = ([MISSING, MISSING, None, "", "red", "#f0a"], ["notacolor", 3, "re\ud83d"])
POINT_POOLS = {
    # Few times, so that many components share one: 1 and 1.0 are the same.
    "time": ([0, 0.0, 0.5, 1, 1.0, 2.5, 59.5, 60, 60.0], [-1.0, 60.5, *ODD_NUMBERS]),
    "label": TEXTS,
    "comments": TEXTS,
    "color": COLORS,
}
PAGE_POOLS = {"page_number": ([1, 2, PAGES], [0, PAGES + 1, 1.5, None, True])}
HARMONY_POOLS = {
    "step": ([MISSING, 0, 3, 6], [7, -1, 1.0]),
    "applied_to": ([MISSING, 0, 4], [7]),
    "accidental": ([MISSING, 0, 1, -2], [3, True]),
    "quality": (
        [MISSING, "major", "minor", "dominant-seventh", "power"],
        ["dominant-seventh-flat-ninth", "maj", None],
    ),
    "inversion": ([MISSING, 0, 1, 2], [3, -1, 1.0]),
    "level": ([MISSING, 1, 2], [0, 3]),
    "display_mode": ([MISSING, "roman", "letter", "custom"], ["roman2"]),
    "custom_text": TEXTS,
    "custom_text_font_type": ([MISSING, "analytic", "normal"], ["bold"]),
}
MODE_POOLS = {
    "step": ([MISSING, 0, 3, 6], [7]),
    "accidental": ([MISSING, 0, -1, 2], [-3]),
    "type": ([MISSING, "major", "minor", "dorian", "locrian"], ["ionian", "x"]),
    "level": ([MISSING, 1, 2], [0]),
}
# Starts and lengths on a grid, moved now and then by less or more than the
# tolerance within which hierarchy boundaries meet.
STARTS = [0, 0.0, 0.5, 1, 1.0, 2, 3, 4]
LENGTHS = [0.5, 1, 1.0, 2, 3, 4]
NOISE = [0] * 8 + [1e-13, -1e-13, 5e-10, -5e-10, 2e-9, -2e-9]
ODD_TIMES = [*ODD_NUMBERS, 61.0, -1.0]
SEGMENT_POOLS = {"label": TEXTS, "comments": TEXTS, "color": COLORS}
LEVELS = ([1, 1, 2, 2, 3, 4], [0, -1, 1.0, 1.5, True, 10**400, None, MISSING])
ROW_IDS = ([ROW, ROW, "Ef34Gh"], ["Zz99Zz", None, MISSING])
TIMELINE_KINDS = ["marker", "beat", "pdf", "harmony", "hierarchy", "range"]
SEEDS = 30
USES = pytest.mark.parametrize(
    "skip_broken", [True, False], ids=["an import", "a reading"]
)


def draw(rng, pools, odds=0.06):
    """Attributes from `pools`: each a usual value or, now and then, an odd one."""
    attrs = {}
    for name, (usual, odd) in pools.items():
        value = rng.choice(odd if rng.random() < odds else usual)
        if value is not MISSING:
            attrs[name] = value
    return attrs


def segment_times(rng):
    if rng.random() < 0.06:
        return rng.choice(ODD_TIMES), rng.choice([2.0, *ODD_TIMES])
    if rng.random() < 0.04:  # an end not after its start
        return 2.0, rng.choice([2.0, 1.0])
    start = rng.choice(STARTS) + rng.choice(NOISE)
    return start, start + rng.choice(LENGTHS) + rng.choice(NOISE)


def margins(rng, attrs):
    """A pre_start and a post_end now and then, within their bounds or not."""
    start, end = attrs["start"], attrs["end"]
    if not (rules._is_number(start) and rules._is_number(end)):
        return
    if rng.random() < 0.15:
        attrs["pre_start"] = rng.choice([None, start, start - 0.25, -1.0, start + 0.25])
    if rng.random() < 0.15:
        attrs["post_end"] = rng.choice([None, end, end + 0.25, end - 0.25, MEDIA + 1])


def random_timeline(kind, seed, size=40):
    """A timeline of `kind`'s components, many of which break a rule."""
    rng = random.Random(f"{kind} {seed}")
    ids = [f"{kind}{n}" for n in range(size)]
    components = []
    for id_ in ids:
        if kind in ("marker", "beat"):
            component_kind, attrs = kind, draw(rng, POINT_POOLS)
        elif kind == "pdf":
            component_kind = "pdf_marker"
            attrs = draw(rng, {**POINT_POOLS, **PAGE_POOLS})
        elif kind == "harmony":
            component_kind = rng.choice(["harmony", "harmony", "mode"])
            pools = HARMONY_POOLS if component_kind == "harmony" else MODE_POOLS
            attrs = draw(rng, {**POINT_POOLS, **pools})
        else:
            component_kind = kind
            start, end = segment_times(rng)
            attrs = {"start": start, "end": end}
            if kind == "hierarchy":
                attrs.update(draw(rng, {"level": LEVELS, **SEGMENT_POOLS}))
            else:
                attrs.update(draw(rng, {"row_id": ROW_IDS, **SEGMENT_POOLS}))
            margins(rng, attrs)
        components.append(tla.Component(id=id_, kind=component_kind, attrs=attrs))
    if kind == "range":
        # Joins: mostly to a range of the row that starts where this one ends,
        # which may or may not be the next one; else to any component.
        for joining in components:
            if rng.random() < 0.6:
                continue
            attrs = joining.attrs
            meeting = [
                other.id
                for other in components
                if other is not joining
                and other.attrs.get("row_id") == attrs.get("row_id")
                and other.attrs["start"] == attrs["end"]
            ]
            pool = meeting if meeting and rng.random() < 0.7 else [*ids, "nope"]
            attrs["joined_right"] = rng.choice(pool)
    return components


def kinds_function(component, others, rows=ROWS):
    """The component's kind's function, as an importer calls it: with a color that
    isn't one replaced by the default. Gives the outcome, and, when it raised
    CantCheck, that exception's cause, shown; else None."""
    attrs = dict(component.attrs)
    if not rules.color(attrs.get("color")):
        del attrs["color"]
    kind = component.kind
    try:
        if kind == "pdf_marker":
            outcome = rules.pdf_marker(MEDIA, others, attrs, page_count=PAGES)
        elif kind == "range":
            outcome = rules.range_(MEDIA, others, attrs, rows=rows)
        else:
            outcome = getattr(rules, kind)(MEDIA, others, attrs)
    except rules.CantCheck as cant_check:
        return rules.OK, repr(cant_check.__cause__)
    return outcome, None


def without_join(component):
    attrs = dict(component.attrs)
    attrs.pop("joined_right", None)
    return tla.Component(id=component.id, kind=component.kind, attrs=attrs)


def found_row_by_row(components, skip_broken, rows=ROWS):
    """What the kinds' functions find, each component checked with every other
    one, or, as an import, with the earlier ones they kept. An import checks a
    range's join once every range is kept or left out by its own rules, with all
    the ranges kept, since a join names a range that starts later."""
    found, kept = {}, []
    ranges_kept = [
        component
        for component in components
        if component.kind == "range"
        and kinds_function(without_join(component), [], rows)[0]
    ]
    for component in components:
        if not skip_broken:
            others = [other for other in components if other is not component]
        elif component.kind == "range":
            others = [other for other in ranges_kept if other is not component]
        else:
            others = list(kept)
        outcome, cant_check = kinds_function(component, others, rows)
        color = rules.color(component.attrs.get("color"))
        found[component.id] = (outcome, outcome.others, color, cant_check)
        if outcome:
            kept.append(component)
    return found


def found_at_once(components, skip_broken, rows=ROWS):
    checked = rules.check_timeline(
        MEDIA, components, rows=rows, page_count=PAGES, skip_broken=skip_broken
    )
    assert list(checked) == [component.id for component in components]
    return {
        id_: (
            c.outcome,
            c.outcome.others,
            c.color,
            None if c.cant_check is None else repr(c.cant_check.__cause__),
        )
        for id_, c in checked.items()
    }


class TestCheckTimeline:
    @USES
    @pytest.mark.parametrize("kind", TIMELINE_KINDS)
    def test_the_kinds_functions_outcomes_on_random_timelines(self, kind, skip_broken):
        # One set of rules: check_timeline finds what the kinds' functions find.
        if kind == "harmony":
            pytest.importorskip("music21", reason="needs the harmony extra")
        for seed in range(SEEDS):
            components = random_timeline(kind, seed)

            found = found_at_once(components, skip_broken)

            assert found == found_row_by_row(components, skip_broken), seed

    @USES
    def test_without_music21_on_random_timelines(self, skip_broken, without_music21):
        for seed in range(SEEDS):
            components = random_timeline("harmony", seed)

            found = found_at_once(components, skip_broken)

            assert found == found_row_by_row(components, skip_broken), seed

    def test_the_random_timelines_break_every_rule_between_components(self):
        # So that the tests above compare what check_timeline finds for each.
        reasons = set()
        for kind in TIMELINE_KINDS:
            if kind == "harmony" and importlib.util.find_spec("music21") is None:
                continue
            for seed in range(SEEDS):
                components = random_timeline(kind, seed)
                for skip_broken in (True, False):
                    found = found_row_by_row(components, skip_broken)
                    reasons |= {
                        outcome.reason.split(" on row")[0]
                        for outcome, others, _, _ in found.values()
                        if others
                    }

        expected = {
            "There is already a marker component at the selected position.",
            "There is already a beat component at the selected position.",
            "There is already a PDF page marker component at the selected position.",
            "There is already a harmony component at the selected position.",
            "There is already a mode component at the selected position.",
            "There is already a hierarchy component at the selected position.",
            "Component would overlap with existing component.",
            "joined_with_next=true but next range",
            "joined_with_next=true but the range it joins isn't the next range",
        }
        if importlib.util.find_spec("music21") is None:
            expected -= {
                "There is already a harmony component at the selected position.",
                "There is already a mode component at the selected position.",
            }
        assert reasons == expected

    def test_each_component_by_its_id_in_the_order_given(self):
        components = [component("marker", time=t) for t in (3.0, 1.0, 2.0)]

        checked = rules.check_timeline(MEDIA, components)

        assert list(checked) == [c.id for c in components]
        assert all(c.outcome == OK and c.color == OK for c in checked.values())

    @pytest.mark.parametrize(
        "first, second, reason",
        [
            (
                component("marker", time=1.0),
                component("marker", time=1),
                "There is already a marker component at the selected position.",
            ),
            (
                hierarchy(0, 10, 1),
                hierarchy(5, 15, 1),
                "Component would overlap with existing component.",
            ),
            (
                hierarchy(0, 10, 1),
                hierarchy(0, 10, 1),
                "There is already a hierarchy component at the selected position.",
            ),
        ],
    )
    def test_the_reading_use_reports_every_broken_pair_naming_both(
        self, first, second, reason
    ):
        checked = rules.check_timeline(MEDIA, [first, second])

        assert checked[first.id].outcome == (False, reason)
        assert checked[first.id].outcome.others == (second.id,)
        assert checked[second.id].outcome == (False, reason)
        assert checked[second.id].outcome.others == (first.id,)

    def test_the_reading_use_names_every_other_at_the_same_time(self):
        markers = [component("marker", time=1.0) for _ in range(3)]

        checked = rules.check_timeline(MEDIA, markers)

        for marker in markers:
            others = tuple(other.id for other in markers if other is not marker)
            assert checked[marker.id].outcome.others == others

    def test_the_import_use_keeps_the_first_of_two_at_the_same_time(self):
        first, second, third = [component("marker", time=t) for t in (1.0, 1.0, 2.0)]

        checked = rules.check_timeline(MEDIA, [first, second, third], skip_broken=True)

        assert checked[first.id].outcome == OK
        assert checked[second.id].outcome == (
            False,
            "There is already a marker component at the selected position.",
        )
        assert checked[second.id].outcome.others == (first.id,)
        assert checked[third.id].outcome == OK

    def test_the_import_use_leaves_a_skipped_component_out_of_what_follows(self):
        # The second crosses the first, and is skipped; the third crosses only
        # the second, so it is kept. Read, both crossings are reported.
        kept, crossing = hierarchy(0, 10, 1), hierarchy(5, 15, 1)
        after = hierarchy(12, 20, 1)
        components = [kept, crossing, after]

        imported = rules.check_timeline(MEDIA, components, skip_broken=True)
        read = rules.check_timeline(MEDIA, components)

        assert [imported[c.id].outcome.ok for c in components] == [True, False, True]
        assert imported[crossing.id].outcome.others == (kept.id,)
        assert [read[c.id].outcome.ok for c in components] == [False, False, False]
        assert read[crossing.id].outcome.others == (kept.id, after.id)

    def test_a_component_that_breaks_its_own_rules_is_left_out_on_import(self):
        level_0, kept = hierarchy(5, 15, 0), hierarchy(0, 10, 1)

        imported = rules.check_timeline(MEDIA, [level_0, kept], skip_broken=True)
        read = rules.check_timeline(MEDIA, [level_0, kept])

        assert imported[level_0.id].outcome == (
            False,
            "Level can't be below 1. Got '0'",
        )
        assert imported[kept.id].outcome == OK
        assert read[kept.id].outcome == (
            False,
            "Component would overlap with existing component.",
        )

    def test_a_single_change_is_checked_on_the_timeline_it_leaves(self):
        # A range put between two joined ranges breaks the first one's join,
        # which checking the new range alone can't tell.
        second = range_in(ROW, 2.0, 3.0)
        first = range_in(ROW, 1.0, 2.0, joined_right=second.id)
        between = range_in(ROW, 1.5, 1.8)
        assert check("range", [first, second], start=1.5, end=1.8) == OK

        checked = rules.check_timeline(MEDIA, [first, second, between], rows=ROWS)

        assert checked[first.id].outcome == (
            False,
            "joined_with_next=true but next range on row 'Strings' starts at 1.5"
            " (must equal 2.0 for ranges to join)",
        )
        assert checked[first.id].outcome.others == (between.id,)
        assert checked[between.id].outcome == OK

    def test_the_import_use_checks_a_join_with_the_range_given_after_it(self):
        # A join names a range that starts later: an import checks it once every
        # range is kept or left out.
        first = range_in(ROW, 1.0, 2.0, joined_right="second")
        second = tla.Component(
            id="second", kind="range", attrs={"start": 2.0, "end": 3.0, "row_id": ROW}
        )

        checked = rules.check_timeline(
            MEDIA, [first, second], rows=ROWS, skip_broken=True
        )

        assert checked[first.id].outcome == OK
        assert checked[second.id].outcome == OK

    def test_the_import_use_checks_a_join_with_every_range_kept(self):
        second = range_in(ROW, 2.0, 3.0)
        first = range_in(ROW, 1.0, 2.0, joined_right=second.id)
        between = range_in(ROW, 1.5, 1.8)  # given last, but it comes next

        checked = rules.check_timeline(
            MEDIA, [first, second, between], rows=ROWS, skip_broken=True
        )

        assert checked[first.id].outcome == (
            False,
            "joined_with_next=true but next range on row 'Strings' starts at 1.5"
            " (must equal 2.0 for ranges to join)",
        )
        assert checked[first.id].outcome.others == (between.id,)

    def test_the_import_use_checks_a_join_without_the_ranges_left_out(self):
        beyond = range_in(ROW, 2.0, 61.0)  # beyond the media: left out
        first = range_in(ROW, 1.0, 2.0, joined_right=beyond.id)

        checked = rules.check_timeline(
            MEDIA, [first, beyond], rows=ROWS, skip_broken=True
        )

        assert checked[beyond.id].outcome == (False, "Range is outside media bounds.")
        assert checked[first.id].outcome == (
            False,
            "joined_with_next=true on last range of row 'Strings';"
            " no next neighbor to join with",
        )

    def test_a_range_whose_join_is_broken_counts_among_the_kept_on_import(self):
        # Until TimeLineAnnotator/project-management#374 settles what a broken
        # join does to its range in an import, the other joins are checked with
        # the range among the kept.
        broken = range_in(ROW, 2.0, 3.0, joined_right="nowhere")
        first = range_in(ROW, 1.0, 2.0, joined_right=broken.id)

        checked = rules.check_timeline(
            MEDIA, [first, broken], rows=ROWS, skip_broken=True
        )

        assert checked[broken.id].outcome == (
            False,
            "joined_with_next=true on last range of row 'Strings';"
            " no next neighbor to join with",
        )
        assert checked[first.id].outcome == OK

    @USES
    def test_a_bad_color_is_reported_and_another_broken_rule_still_found(
        self, skip_broken
    ):
        broken = hierarchy(1, 2, 0, color="notacolor")

        checked = rules.check_timeline(MEDIA, [broken], skip_broken=skip_broken)

        assert checked[broken.id].outcome == (False, "Level can't be below 1. Got '0'")
        assert checked[broken.id].color == (False, "notacolor is not a valid color.")

    def test_a_component_whose_only_broken_rule_is_its_color_is_kept_on_import(self):
        # An importer keeps it, with the default color.
        colored = component("marker", time=1.0, color="notacolor")
        later = component("marker", time=1.0)

        checked = rules.check_timeline(MEDIA, [colored, later], skip_broken=True)

        assert checked[colored.id].outcome == OK
        assert checked[colored.id].color == (False, "notacolor is not a valid color.")
        assert checked[later.id].outcome.others == (colored.id,)

    @pytest.mark.parametrize("value", ["#f0a", None, "", MISSING])
    def test_the_default_color_or_one_qt_reads(self, value):
        attrs = {} if value is MISSING else {"color": value}
        marker = component("marker", time=1.0, **attrs)

        assert rules.check_timeline(MEDIA, [marker])[marker.id].color == OK

    def test_a_color_with_a_lone_surrogate_is_reported(self):
        # A file can hold one, written as \ud83d.
        marker = component("marker", time=1.0, color="re\ud83d")

        checked = rules.check_timeline(MEDIA, [marker])[marker.id]

        assert checked.color == (False, "re\ud83d is not a valid color.")

    def test_music21_is_looked_up_once_per_call(self, music21, monkeypatch):
        calls = []
        look_up = rules._music21

        def counted():
            calls.append(1)
            return look_up()

        monkeypatch.setattr(rules, "_music21", counted)
        components = [component("harmony", time=float(t)) for t in range(5)]
        components += [component("mode", time=float(t)) for t in range(5)]

        rules.check_timeline(MEDIA, components)
        assert len(calls) == 1
        rules.check_timeline(MEDIA, components, skip_broken=True)
        assert len(calls) == 2

    def test_music21_isnt_looked_up_without_harmonies_or_keys(self, monkeypatch):
        def fail():
            raise AssertionError("looked up music21")

        monkeypatch.setattr(rules, "_music21", fail)
        components = [component("marker", time=1.0), hierarchy(0, 1, 1)]

        rules.check_timeline(MEDIA, components)

    def test_music21_installed_since_the_last_call_is_found(self, music21, monkeypatch):
        harmony = component("harmony", time=1.0, quality="maj")

        with monkeypatch.context() as uninstalled:
            uninstall_music21(uninstalled)
            assert rules.check_timeline(MEDIA, [harmony])[harmony.id].cant_check

        checked = rules.check_timeline(MEDIA, [harmony])[harmony.id]
        assert checked.cant_check is None
        assert checked.outcome == (False, "maj is not a valid quality.")

    @USES
    @pytest.mark.parametrize("kind", ["harmony", "mode"])
    def test_without_music21_it_reports_what_cant_be_checked(
        self, kind, skip_broken, without_music21
    ):
        unchecked = component(kind, time=1.0, color="notacolor")
        broken = component(kind, time=2.0, level=3)

        checked = rules.check_timeline(
            MEDIA, [unchecked, broken], skip_broken=skip_broken
        )

        cant_check = checked[unchecked.id].cant_check
        assert isinstance(cant_check, rules.CantCheck)
        assert cant_check.kind == kind
        assert cant_check.command == INSTALL
        assert INSTALL in str(cant_check)
        assert checked[unchecked.id].outcome == OK
        assert checked[unchecked.id].color == (
            False,
            "notacolor is not a valid color.",
        )
        assert checked[broken.id].outcome == (False, "3 is not a valid level.")
        assert checked[broken.id].cant_check is None

    def test_without_music21_one_that_cant_be_checked_is_kept_on_import(
        self, without_music21
    ):
        first, second = component("harmony", time=1.0), component("harmony", time=1.0)

        checked = rules.check_timeline(MEDIA, [first, second], skip_broken=True)

        assert checked[first.id].cant_check is not None
        assert checked[second.id].outcome.others == (first.id,)
        assert checked[second.id].cant_check is None

    @pytest.mark.parametrize(
        "missing, cause",
        [
            ("without_music21", type(None)),
            ("broken_music21", ImportError),
            ("music21_raising", AttributeError),
        ],
    )
    @pytest.mark.parametrize("kind", ["harmony", "mode"])
    def test_cant_check_has_the_cause_the_kinds_function_raises_it_from(
        self, request, missing, cause, kind
    ):
        request.getfixturevalue(missing)
        unchecked = component(kind, time=1.0)
        with pytest.raises(rules.CantCheck) as raised:
            getattr(rules, kind)(MEDIA, [], unchecked.attrs)

        cant_check = rules.check_timeline(MEDIA, [unchecked])[unchecked.id].cant_check

        assert isinstance(cant_check.__cause__, cause)
        assert repr(cant_check.__cause__) == repr(raised.value.__cause__)

    def test_ranges_need_the_rows(self):
        with pytest.raises(TypeError, match="rows"):
            rules.check_timeline(MEDIA, [range_in(ROW, 1.0, 2.0)])

    def test_pdf_markers_need_the_page_count(self):
        marker = component("pdf_marker", time=1.0, page_number=1)

        with pytest.raises(TypeError, match="page count"):
            rules.check_timeline(MEDIA, [marker])

    def test_other_kinds_need_neither(self):
        checked = rules.check_timeline(MEDIA, [component("marker", time=1.0)])

        assert len(checked) == 1

    @pytest.mark.parametrize("kind", ["note", tla.UnknownKind("MARKERS")])
    def test_kinds_the_rules_dont_cover_are_left_out(self, kind):
        other = tla.Component(id="other", kind=kind, attrs={"time": 1.0})
        marker = component("marker", time=1.0)

        checked = rules.check_timeline(MEDIA, [other, marker])

        assert list(checked) == [marker.id]
        assert checked[marker.id].outcome == OK

    def test_one_table_gives_each_kind_its_rules(self, monkeypatch):
        # The kinds' functions and check_timeline find a kind's rules in one
        # place, so a kind can't get rules of its own in one of them.
        def refused(*args):
            return rules.Outcome(False, "refused")

        kinds = [
            "marker",
            "beat",
            "pdf_marker",
            "harmony",
            "mode",
            "hierarchy",
            "range",
        ]
        assert sorted(rules._RULES) == sorted(kinds)
        for kind in kinds:
            monkeypatch.setitem(rules._RULES, kind, refused)
        for kind in kinds:
            checked = component(kind, **VALID[kind])

            found = rules.check_timeline(MEDIA, [checked], rows=ROWS, page_count=PAGES)

            assert kinds_function(checked, [])[0] == (False, "refused"), kind
            assert found[checked.id].outcome == (False, "refused"), kind

    def test_two_components_with_one_id(self):
        first = component("marker", time=1.0)
        second = tla.Component(id=first.id, kind="marker", attrs={"time": 2.0})

        with pytest.raises(ValueError, match=first.id):
            rules.check_timeline(MEDIA, [first, second])

    @USES
    @pytest.mark.parametrize(
        "components, rows",
        [
            # Values that can't be hashed, as the time or the level.
            (
                [
                    component("marker", time=[1.0]),
                    component("marker", time=1.0),
                    hierarchy(1.0, 2.0, [1]),
                    hierarchy(1.0, 2.0, 1),
                ],
                ROWS,
            ),
            # A row whose id is a list, which only a caller in Python can give.
            (
                [
                    range_in(["odd"], 1.0, 2.0, joined_right="second"),
                    tla.Component(
                        id="second",
                        kind="range",
                        attrs={"start": 2.0, "end": 3.0, "row_id": ["odd"]},
                    ),
                    range_in(["odd"], 1.5, 4.0, joined_right="second"),
                ],
                [*ROWS, {"id": ["odd"], "name": "Odd"}],
            ),
            # A row whose id is a frozenset, which a set equals, and the other
            # way round: one can be hashed, the other can't.
            (
                [
                    range_in(frozenset({"x"}), 1.0, 2.0, joined_right="set"),
                    tla.Component(
                        id="set",
                        kind="range",
                        attrs={"start": 2.0, "end": 3.0, "row_id": {"x"}},
                    ),
                    range_in({"x"}, 3.0, 4.0, joined_right="frozenset"),
                    tla.Component(
                        id="frozenset",
                        kind="range",
                        attrs={"start": 4.0, "end": 5.0, "row_id": frozenset({"x"})},
                    ),
                ],
                [*ROWS, {"id": frozenset({"x"}), "name": "Set"}],
            ),
            # True, which is 1, but isn't a time the others are ordered by.
            (
                [
                    component("marker", time=True),
                    component("marker", time=1),
                    hierarchy(True, 2.0, 1),
                    hierarchy(1, 2.0, 1),
                    hierarchy(1, 2.0, True),
                    hierarchy(0.5, 2.0, 2),
                ],
                ROWS,
            ),
            # Other values equal to a number: some can be ordered with one,
            # one can't.
            (
                [
                    component("marker", time=Decimal("1")),
                    component("marker", time=1 + 0j),
                    component("marker", time=1.0),
                    hierarchy(Decimal("1"), 2.0, 1),
                    hierarchy(Fraction(1), 2, 1),
                    hierarchy(1 + 0j, 2.0, 1),
                    hierarchy(1, 2.0, 1),
                ],
                ROWS,
            ),
        ],
        ids=["unhashable", "unhashable row id", "set", "true", "numbers"],
    )
    def test_odd_values_are_compared_as_the_functions_compare_them(
        self, components, rows, skip_broken
    ):
        found = found_at_once(components, skip_broken, rows)

        assert found == found_row_by_row(components, skip_broken, rows)

    def test_the_components_are_left_as_they_are(self):
        components = random_timeline("range", 0)
        before = copy.deepcopy(components)

        rules.check_timeline(MEDIA, components, rows=ROWS)

        assert repr(components) == repr(before)


def nested_hierarchies(total, length):
    """`total` hierarchies that nest: five at level 4, each split in five at
    levels 3 and 2, and level 2's spans split among the rest, at level 1."""

    def split(start, end, pieces):
        bounds = [start + (end - start) * n / pieces for n in range(pieces)] + [end]
        return list(itertools.pairwise(bounds))

    parents = split(0.0, length, 5)
    spans = [(start, end, 4) for start, end in parents]
    for level in (3, 2):
        parents = [piece for start, end in parents for piece in split(start, end, 5)]
        spans += [(start, end, level) for start, end in parents]
    rest = total - len(spans)
    for n, (start, end) in enumerate(parents):
        pieces = rest // len(parents) + (n < rest % len(parents))
        spans += [(s, e, 1) for s, e in split(start, end, pieces)]
    assert len(spans) == total
    return [hierarchy(*span) for span in spans]


def fastest(run, times=3):
    """What `run` gives, and the fewest seconds it took in `times` runs."""
    seconds = []
    for _ in range(times):
        start = time.perf_counter()
        result = run()
        seconds.append(time.perf_counter() - start)
    return result, min(seconds)


# "Well under a second", for each timeline below.
WELL_UNDER_A_SECOND = 0.5


@pytest.mark.benchmark
class TestCheckTimelineSpeed:
    @USES
    def test_10000_beats(self, skip_broken):
        beats = [component("beat", time=n * 0.25) for n in range(10_000)]

        checked, seconds = fastest(
            lambda: rules.check_timeline(2500.0, beats, skip_broken=skip_broken)
        )

        use = "imported" if skip_broken else "read"
        print(f"10,000 beats, {use}: {seconds:.3f} s")
        assert all(c.outcome for c in checked.values())
        assert seconds < WELL_UNDER_A_SECOND

    @USES
    def test_3000_hierarchies_with_nesting(self, skip_broken):
        hierarchies = nested_hierarchies(3000, 3000.0)
        random.Random(303).shuffle(hierarchies)

        checked, seconds = fastest(
            lambda: rules.check_timeline(3000.0, hierarchies, skip_broken=skip_broken)
        )

        use = "imported" if skip_broken else "read"
        print(f"3,000 hierarchies with nesting, {use}: {seconds:.3f} s")
        assert all(c.outcome for c in checked.values())
        assert seconds < WELL_UNDER_A_SECOND

    @USES
    def test_10000_beats_at_one_time_that_break_a_rule_of_their_own(self, skip_broken):
        # The others at their time are looked for only once their own rules
        # are kept, which they never are.
        beats = [component("beat", time=0.0, label=3) for _ in range(10_000)]

        checked, seconds = fastest(
            lambda: rules.check_timeline(2500.0, beats, skip_broken=skip_broken)
        )

        use = "imported" if skip_broken else "read"
        print(
            f"10,000 beats at one time, each with a label of 3, {use}: {seconds:.3f} s"
        )
        assert {c.outcome for c in checked.values()} == {
            (False, "3 is not a valid label.")
        }
        assert seconds < WELL_UNDER_A_SECOND

    @USES
    def test_3000_hierarchies_at_one_place_that_break_a_rule_of_their_own(
        self, skip_broken
    ):
        hierarchies = [hierarchy(0.0, 10.0, 0) for _ in range(3000)]

        checked, seconds = fastest(
            lambda: rules.check_timeline(MEDIA, hierarchies, skip_broken=skip_broken)
        )

        use = "imported" if skip_broken else "read"
        print(
            f"3,000 hierarchies at one place, each at level 0, {use}: {seconds:.3f} s"
        )
        assert {c.outcome for c in checked.values()} == {
            (False, "Level can't be below 1. Got '0'")
        }
        assert seconds < WELL_UNDER_A_SECOND

    def test_3000_hierarchies_that_cross_the_first_on_import(self):
        # Each is checked with the hierarchies kept, not with every earlier one:
        # every one after the first crosses it, and every other one.
        hierarchies = [hierarchy(0.0, 10.0, 1)]
        hierarchies += [
            hierarchy(5.0 + n / 1000, 15.0 + n / 1000, 1) for n in range(2999)
        ]

        checked, seconds = fastest(
            lambda: rules.check_timeline(MEDIA, hierarchies, skip_broken=True)
        )

        print(f"3,000 hierarchies crossing the first, imported: {seconds:.3f} s")
        others = [c.outcome.others for c in checked.values()]
        assert others[1:] == [(hierarchies[0].id,)] * 2999
        assert seconds < WELL_UNDER_A_SECOND
