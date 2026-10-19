import copy
import importlib.util
import itertools
import pickle
import sys
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
def without_music21(monkeypatch):
    find_spec = importlib.util.find_spec

    def find_spec_without_music21(name, *args, **kwargs):
        if name.partition(".")[0] == "music21":
            return None
        return find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec_without_music21)


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


def tilia_boundary_conflicts(hierarchies):
    """`HierarchyTLComponentManager.get_boundary_conflicts`, on (start, end, level)s."""
    conflicts = []
    for hrc1, hrc2 in itertools.combinations(hierarchies, 2):
        start1, end1, level1 = hrc1
        start2, end2, level2 = hrc2
        if start1 < start2 < end1 or start1 < end2 < end1:
            if level2 >= level1:
                conflicts.append((hrc1, hrc2))
            elif not start1 > start2 and end1 < end2:
                conflicts.append((hrc1, hrc2))
        if start2 < start1 < end2 or start2 < end1 < end2:
            if level1 >= level2:
                conflicts.append((hrc2, hrc1))
            elif not start2 > start1 and end2 < end1:
                conflicts.append((hrc2, hrc1))
        if start1 == start2 and end1 == end2 and level1 == level2:
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

    def test_if_reads_as_keeping_to_the_rules(self):
        assert rules.marker(60.0, [], {"time": 1.0})
        assert not rules.marker(60.0, [], {"time": -1.0})
        assert not rules.hierarchy(60.0, [], {"start": 0.0, "end": 1.0, "level": 0})

    def test_a_check_that_keeps_doesnt_end_the_checks(self):
        broken = rules.Outcome(False, "Invalid row ID.")

        assert rules._kept({}, lambda: rules.OK, lambda: broken) == broken

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

    def test_a_broken_rule_names_the_other_components(self):
        outcome = rules.Outcome(False, "Component would overlap", ["a", "b"])

        assert outcome == (False, "Component would overlap")
        assert outcome.others == ("a", "b")
        assert (outcome.ok, outcome.reason) == (False, "Component would overlap")


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
            0,
            True,
        ],
    )
    def test_a_color_that_isnt_one(self, value):
        assert rules.color(value) == (False, f"{value} is not a valid color.")

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

    def test_numbers_given_as_integers_read_as_tilias_floats(self):
        assert check("hierarchy", start=61, end=62, media_length=60) == (
            False,
            "Start time '61.0' is bigger than media time '60.0'",
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
