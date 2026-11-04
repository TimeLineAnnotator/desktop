"""The core's rules for a valid component, when a file is read and when a
document is written (FR-053, FR-054): reading keeps a component that breaks
one, with one warning per broken rule; writing refuses a new problem, and
writes back unchanged the problems a file came with."""

import copy
import dataclasses
import importlib.util
import json
import pickle
import sys
from pathlib import Path

import pytest

from tilia_core import rules, tla
from tilia_core.tla import writer

BROKEN = Path(__file__).parent / "broken"
OLD = Path(__file__).parent / "old"
GOLDEN = Path(__file__).parent / "golden"


def _load_make_broken():
    spec = importlib.util.spec_from_file_location(
        "make_broken", BROKEN / "make_broken.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


make_broken = _load_make_broken()
IDS = make_broken.IDS
make_id = make_broken.make_id
FIRST, SECOND, THIRD, FOURTH = (make_id(100 + n) for n in range(4))
FORM = IDS["form"]
SECTION = IDS["section"]
CADENCES = IDS["cadences"]
CADENCE = IDS["cadence"]
BEATS = IDS["beats"]
TEXTURE = IDS["texture"]
MELODY_1, MELODY_2 = IDS["melody_1"], IDS["melody_2"]
ROW = "aZ3k9P"
HARMONIES = make_id(110)
PDF = make_id(111)
INSTALL = 'pip install "tilia-core[harmony]"'
OVERLAP = "Component would overlap with existing component."


def a_file(change=None):
    content = copy.deepcopy(make_broken.base())
    if change is not None:
        change(content)
    return make_broken.text_of(content).encode("utf-8")


def hierarchies(*components):
    """A change: the Form timeline holds these hierarchies, given as
    (id, attributes), in id order."""

    def change(content):
        content["timelines"][FORM]["components"] = {
            key: {"kind": "HIERARCHY", **attrs} for key, attrs in components
        }

    return change


def at_level(start, end, level, **attrs):
    return {"start": start, "end": end, "level": level, **attrs}


def markers(*components):
    def change(content):
        content["timelines"][CADENCES]["components"] = {
            key: {"kind": "MARKER", **attrs} for key, attrs in components
        }

    return change


def harmony_timeline(*components):
    def change(content):
        content["timelines"][HARMONIES] = {
            "kind": "Harmony",
            "name": "Keys",
            "ordinal": 6,
            "height": 30,
            "components": dict(components),
        }

    return change


def harmony(time, **attrs):
    return {"kind": "HARMONY", "time": time, **attrs}


def mode(time, **attrs):
    return {"kind": "MODE", "time": time, **attrs}


def with_media_length(length):
    def change(content):
        content["media"]["length"] = length

    return change


def together(*changes):
    def change(content):
        for one in changes:
            one(content)

    return change


LEVEL_0 = hierarchies((FIRST, at_level(0.0, 2.0, 0)))
CROSSING = hierarchies(
    (FIRST, at_level(0.0, 2.0, 1)),
    (SECOND, at_level(1.0, 3.0, 1)),
)


def component_place(timeline, component):
    return f"/timelines/{timeline}/components/{component}"


def line_of(data, key):
    """The line of the key `key` in a file's bytes."""
    lines = data.decode("utf-8").split("\n")
    return next(n for n, line in enumerate(lines, 1) if f'"{key}":' in line)


def named(data, *keys, timeline=FORM):
    """How a warning names other components, given by id."""
    others = "; ".join(
        f"line {line_of(data, key)}, {component_place(timeline, key)}" for key in keys
    )
    what = "other components" if len(keys) > 1 else "other component"
    return f"({what}: {others})"


@pytest.fixture
def without_music21(monkeypatch):
    find_spec = importlib.util.find_spec

    def find_spec_without_music21(name, *args, **kwargs):
        if name.partition(".")[0] == "music21":
            return None
        return find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec_without_music21)


@pytest.fixture
def music21():
    return pytest.importorskip("music21", reason="needs the harmony extra")


# Reading


class TestReading:
    def test_a_file_that_keeps_to_the_rules_has_no_warning(self):
        doc = tla.loads(a_file())
        assert doc.warnings == []
        assert doc.read_problems == []

    def test_a_hierarchy_at_level_0_is_kept_with_one_warning(self):
        data = a_file(LEVEL_0)
        doc = tla.loads(data)
        assert doc.warnings == [
            tla.ReadWarning(
                place=component_place(FORM, FIRST),
                line=line_of(data, FIRST),
                message="Level can't be below 1. Got '0'",
            )
        ]
        assert doc.timelines[FORM].components[FIRST].attrs["level"] == 0

    def test_two_hierarchies_that_cross_have_one_warning_naming_the_other(self):
        data = a_file(CROSSING)
        assert tla.loads(data).warnings == [
            tla.ReadWarning(
                place=component_place(FORM, FIRST),
                line=line_of(data, FIRST),
                message=f"{OVERLAP} {named(data, SECOND)}",
            )
        ]

    def test_each_pair_that_crosses_is_named_once(self):
        data = a_file(
            hierarchies(
                (FIRST, at_level(0.0, 2.0, 1)),
                (SECOND, at_level(1.0, 3.0, 1)),
                (THIRD, at_level(1.5, 4.0, 1)),
            )
        )
        assert [(w.place, w.message) for w in tla.loads(data).warnings] == [
            (
                component_place(FORM, FIRST),
                f"{OVERLAP} {named(data, SECOND, THIRD)}",
            ),
            (component_place(FORM, SECOND), f"{OVERLAP} {named(data, THIRD)}"),
        ]

    def test_a_hierarchy_that_crosses_many_names_the_first_ten(self):
        ids = [make_id(200 + n) for n in range(13)]
        data = a_file(
            hierarchies(
                (FIRST, at_level(0.0, 2.0, 1)),
                *((key, at_level(1.0, 3.0 + n, 1)) for n, key in enumerate(ids)),
            )
        )
        first = tla.loads(data).warnings[0]
        assert first.place == component_place(FORM, FIRST)
        assert first.message == (
            f"{OVERLAP} {named(data, *ids[:10])[:-1]}; and 3 more)"
        )

    def test_two_markers_at_one_time_have_one_warning_naming_the_other(self):
        data = a_file(
            markers((FIRST, {"time": 1.0}), (SECOND, {"time": 1.0, "label": "b"}))
        )
        assert tla.loads(data).warnings == [
            tla.ReadWarning(
                place=component_place(CADENCES, FIRST),
                line=line_of(data, FIRST),
                message="There is already a marker component at the selected position."
                f" {named(data, SECOND, timeline=CADENCES)}",
            )
        ]

    def test_two_beats_at_one_time_are_both_kept_with_a_warning_naming_them(self):
        def change(content):
            components = content["timelines"][BEATS]["components"]
            components[IDS["beat_2"]]["time"] = 0.0

        data = a_file(change)
        doc = tla.loads(data)
        assert doc.warnings == [
            tla.ReadWarning(
                place=component_place(BEATS, IDS["beat_1"]),
                line=line_of(data, IDS["beat_1"]),
                message="There is already a beat component at the selected position."
                f" {named(data, IDS['beat_2'], timeline=BEATS)}",
            )
        ]
        assert len(doc.timelines[BEATS].components) == 2

    def test_a_harmony_and_a_mode_at_one_time_are_not_compared(self, music21):
        doc = tla.loads(
            a_file(harmony_timeline((FIRST, harmony(1.0)), (SECOND, mode(1.0))))
        )
        assert doc.warnings == []

    def test_every_rule_a_component_breaks_has_its_own_warning(self):
        data = a_file(hierarchies((FIRST, at_level(2.0, 3.0, 0, pre_start=2.5))))
        place = component_place(FORM, FIRST)
        line = line_of(data, FIRST)
        assert tla.loads(data).warnings == [
            tla.ReadWarning(place, line, "Level can't be below 1. Got '0'"),
            tla.ReadWarning(place, line, "pre_start can't be after start time."),
        ]

    def test_a_crossing_is_named_even_when_both_are_at_level_0(self):
        data = a_file(
            hierarchies(
                (FIRST, at_level(0.0, 2.0, 0)),
                (SECOND, at_level(1.0, 3.0, 0)),
            )
        )
        assert [w.message for w in tla.loads(data).warnings] == [
            "Level can't be below 1. Got '0'",
            f"{OVERLAP} {named(data, SECOND)}",
            "Level can't be below 1. Got '0'",
        ]

    def test_a_color_that_isnt_one_has_its_own_warning_after_the_others(self):
        data = a_file(hierarchies((FIRST, at_level(0.0, 2.0, 0, color="notacolor"))))
        assert [w.message for w in tla.loads(data).warnings] == [
            "Level can't be below 1. Got '0'",
            "notacolor is not a valid color.",
        ]

    def test_a_broken_join_is_warned_about_on_the_range_that_joins(self):
        def change(content):
            components = content["timelines"][TEXTURE]["components"]
            components[MELODY_2]["start"] = 1.5

        data = a_file(change)
        assert tla.loads(data).warnings == [
            tla.ReadWarning(
                place=component_place(TEXTURE, MELODY_1),
                line=line_of(data, MELODY_1),
                message="joined_with_next=true but next range on row 'Melody' starts"
                " at 1.5 (must equal 1.0 for ranges to join)"
                f" {named(data, MELODY_2, timeline=TEXTURE)}",
            )
        ]

    def test_a_row_that_breaks_a_rule_is_warned_about_in_its_place(self):
        def change(content):
            content["timelines"][TEXTURE]["rows"].append(
                {"id": "Ab-12", "name": "Bass", "color": "notacolor"}
            )

        data = a_file(change)
        place = f"/timelines/{TEXTURE}/rows/1"
        line = data.decode().split("\n").index('          "id": "Ab-12",')
        assert tla.loads(data).warnings == [
            tla.ReadWarning(place, line, "Ab-12 is not a valid row id."),
            tla.ReadWarning(place, line, "notacolor is not a valid color."),
        ]

    def test_a_component_the_rules_dont_cover_is_not_checked(self):
        # Known to the core, but not one its timeline holds: kept as it is,
        # with the check's warning alone.
        def change(content):
            content["timelines"][FORM]["components"][FIRST] = {
                "kind": "MARKER",
                "time": -1.0,
            }

        warnings = tla.loads(a_file(change)).warnings
        assert len(warnings) == 1
        assert "MARKER" in warnings[0].message

    def test_a_lone_surrogate_in_a_reason_can_be_printed(self):
        content = json.loads(a_file(markers((FIRST, {"time": 1.0, "color": "x"}))))
        content["timelines"][CADENCES]["components"][FIRST]["color"] = "re\ud83d"
        doc = tla.loads(json.dumps(content).encode())
        assert doc.warnings[0].message == "re\\ud83d is not a valid color."
        str(doc.warnings[0]).encode("utf-8")

    def test_a_file_in_another_layout_has_the_lines_of_its_own_text(self):
        content = json.loads(a_file(LEVEL_0))
        data = json.dumps(content, ensure_ascii=False).encode("utf-8")
        assert tla.loads(data).warnings[0].line == 1


class TestMediaLength:
    def test_a_time_beyond_the_media_length_is_warned_about(self):
        doc = tla.loads(
            a_file(together(with_media_length(60.0), markers((FIRST, {"time": 61.0}))))
        )
        assert [w.message for w in doc.warnings] == [
            "Time '01:01.0' is bigger than media time '01:00.0'"
        ]

    def test_with_an_unknown_length_no_time_is_beyond_it(self):
        assert tla.loads(a_file(markers((FIRST, {"time": 1e6})))).warnings == []

    def test_a_quarters_file_has_no_media_length_to_compare_with(self):
        # FR-080: its times are in quarter notes, and a media length in seconds.
        def change(content):
            content["time_unit"] = "quarters"
            content["media"]["length"] = 60.0

        doc = tla.loads(a_file(together(change, markers((FIRST, {"time": 61.0})))))
        assert doc.warnings == []

    @pytest.mark.parametrize(
        "length, shown",
        [
            (0, "0"),
            (0.0, "0.0"),
            (-5.0, "-5.0"),
            (10**400, str(10**400)),
            (-(10**400), str(-(10**400))),
        ],
    )
    def test_a_length_that_isnt_one_is_warned_about_once(self, length, shown):
        # TimeLineAnnotator/project-management#424: the components aren't
        # compared with it.
        data = a_file(with_media_length(length))
        assert tla.loads(data).warnings == [
            tla.ReadWarning(
                place="/media/length",
                line=line_of(data, "length"),
                message=f"{shown} is not a valid media length.",
            )
        ]

    def test_a_length_that_isnt_one_is_written_back_unchanged(self, tmp_path):
        data = a_file(with_media_length(-5.0))
        path = tmp_path / "piece.tla"
        tla.write(path, tla.loads(data))
        assert path.read_bytes() == data

    @pytest.mark.parametrize("length", [0, -5.0, 10**400])
    def test_a_new_length_that_isnt_one_is_refused(self, tmp_path, length):
        doc = tla.loads(a_file())
        doc.media_length = length
        with pytest.raises(tla.BrokenRules) as refused:
            tla.write(tmp_path / "piece.tla", doc)
        assert [w.place for w in refused.value.problems] == ["/media/length"]

    def test_a_length_that_isnt_one_can_be_fixed(self, tmp_path):
        doc = tla.loads(a_file(with_media_length(-5.0)))
        doc.media_length = 60.0
        tla.write(tmp_path / "piece.tla", doc)
        assert tla.read(tmp_path / "piece.tla").warnings == []


class TestPdfMarkers:
    # TimeLineAnnotator/project-management#423: the PDF isn't opened when a
    # file is read or written, so a page number is checked against its own
    # rules, not against the pages the PDF has.

    @staticmethod
    def pdf_markers(*components):
        def change(content):
            content["timelines"][PDF] = {
                "kind": "Pdf",
                "name": "Score",
                "ordinal": 6,
                "height": 30,
                "path": "missing.pdf",
                "components": {
                    key: {"kind": "PDF_MARKER", **attrs} for key, attrs in components
                },
            }

        return change

    def test_a_page_number_below_1_is_warned_about(self):
        doc = tla.loads(
            a_file(self.pdf_markers((FIRST, {"time": 1.0, "page_number": 0})))
        )
        assert [w.message for w in doc.warnings] == [
            "The PDF has no page with that number."
        ]

    def test_a_pdf_that_cant_be_found_breaks_no_rule(self):
        doc = tla.loads(
            a_file(self.pdf_markers((FIRST, {"time": 1.0, "page_number": 10**6})))
        )
        assert doc.warnings == []


class TestBeatPattern:
    @staticmethod
    def with_pattern(pattern):
        def change(content):
            timeline = content["timelines"][BEATS]
            components = timeline.pop("components")
            timeline["beat_pattern"] = pattern
            timeline["components"] = components

        return change

    def test_one_that_doesnt_parse_is_kept_with_a_warning_naming_the_timeline(self):
        data = a_file(self.with_pattern("abc"))
        doc = tla.loads(data)
        assert doc.warnings == [
            tla.ReadWarning(
                place=f"/timelines/{BEATS}/beat_pattern",
                line=line_of(data, "beat_pattern"),
                message='the beat pattern "abc" of the timeline "Beats"'
                " isn't a valid pattern",
            )
        ]
        assert doc.timelines[BEATS].attrs["beat_pattern"] == "abc"

    @pytest.mark.parametrize("pattern", ["10[", ""])
    def test_one_that_more_typing_could_complete_is_kept_with_a_warning(self, pattern):
        doc = tla.loads(a_file(self.with_pattern(pattern)))
        assert [w.place for w in doc.warnings] == [f"/timelines/{BEATS}/beat_pattern"]

    @pytest.mark.parametrize("pattern", ["4", "10[4] 3", None])
    def test_one_that_parses_has_no_warning(self, pattern):
        assert tla.loads(a_file(self.with_pattern(pattern))).warnings == []

    def test_one_that_doesnt_parse_is_written_back_unchanged(self, tmp_path):
        data = a_file(self.with_pattern("abc"))
        path = tmp_path / "piece.tla"
        tla.write(path, tla.loads(data))
        assert path.read_bytes() == data

    def test_a_new_one_is_refused(self, tmp_path):
        doc = tla.loads(a_file())
        doc.timelines[BEATS].attrs["beat_pattern"] = "abc"
        path = tmp_path / "piece.tla"
        with pytest.raises(tla.BrokenRules):
            tla.write(path, doc)
        assert not path.exists()

    def test_a_changed_one_is_refused(self, tmp_path):
        doc = tla.loads(a_file(self.with_pattern("abc")))
        doc.timelines[BEATS].attrs["beat_pattern"] = "def"
        with pytest.raises(tla.BrokenRules) as refused:
            tla.write(tmp_path / "piece.tla", doc)
        assert refused.value.problems[0].message == (
            'the beat pattern "def" of the timeline "Beats" isn\'t a valid pattern'
        )

    def test_one_that_is_fixed_is_written(self, tmp_path):
        doc = tla.loads(a_file(self.with_pattern("abc")))
        doc.timelines[BEATS].attrs["beat_pattern"] = "3"
        tla.write(tmp_path / "piece.tla", doc)
        assert tla.read(tmp_path / "piece.tla").warnings == []


# Writing


class TestWriting:
    @pytest.mark.parametrize("change", [LEVEL_0, CROSSING])
    def test_a_file_written_back_unchanged_gives_the_same_bytes(self, change, tmp_path):
        data = a_file(change)
        path = tmp_path / "piece.tla"
        doc = tla.loads(data)
        warnings = list(doc.warnings)
        fingerprint = tla.write(path, doc)
        assert path.read_bytes() == data
        assert fingerprint == tla.fingerprint(path)
        assert doc.warnings == warnings
        assert tla.read(path).warnings == warnings

    def test_a_change_to_the_component_that_breaks_a_rule_is_refused(self, tmp_path):
        data = a_file(LEVEL_0)
        doc = tla.loads(data)
        doc.timelines[FORM].components[FIRST].attrs["label"] = "A"
        path = tmp_path / "piece.tla"
        with pytest.raises(tla.BrokenRules) as refused:
            tla.write(path, doc)
        assert not path.exists()
        assert refused.value.path == path
        problems = refused.value.problems
        assert [(w.place, w.message) for w in problems] == [
            (component_place(FORM, FIRST), "Level can't be below 1. Got '0'")
        ]
        # The line in what would have been written.
        assert problems[0].line == line_of(writer.checked_bytes(doc), FIRST)

    @pytest.mark.parametrize("changed", [FIRST, SECOND])
    def test_a_change_to_either_of_two_that_cross_is_refused(self, changed, tmp_path):
        doc = tla.loads(a_file(CROSSING))
        doc.timelines[FORM].components[changed].attrs["label"] = "A"
        path = tmp_path / "piece.tla"
        with pytest.raises(tla.BrokenRules) as refused:
            tla.write(path, doc)
        assert not path.exists()
        problems = refused.value.problems
        assert [w.place for w in problems] == [component_place(FORM, FIRST)]
        assert problems[0].message.startswith(OVERLAP)
        assert component_place(FORM, SECOND) in problems[0].message

    def test_a_refused_write_leaves_the_file_as_it_was(self, tmp_path):
        data = a_file(LEVEL_0)
        path = tmp_path / "piece.tla"
        path.write_bytes(data)
        doc = tla.read(path)
        doc.timelines[FORM].components[FIRST].attrs["end"] = 3.0
        kept = list(doc.read_problems)
        with pytest.raises(tla.BrokenRules):
            tla.write(path, doc)
        assert path.read_bytes() == data
        assert doc.read_problems == kept

    def test_broken_rules_come_before_the_file_is_looked_at(self, tmp_path):
        doc = tla.loads(a_file())
        doc.timelines[FORM].components[FIRST] = tla.Component(
            id=FIRST,
            kind="hierarchy",
            attrs=at_level(1.0, 3.0, 1),
        )
        path = tmp_path / "piece.tla"
        path.write_bytes(b"something else")
        with pytest.raises(tla.BrokenRules):
            tla.write(path, doc, expect=tla.ABSENT)
        assert path.read_bytes() == b"something else"

    @pytest.mark.parametrize(
        "edit",
        [
            lambda c: c.metadata.update(tags=["checked"]),
            lambda c: c.extra.update(unknown=1),
            lambda c: c.attrs.update(comments="a comment"),
        ],
    )
    def test_any_change_to_a_component_counts(self, edit, tmp_path):
        doc = tla.loads(a_file(LEVEL_0))
        edit(doc.timelines[FORM].components[FIRST])
        with pytest.raises(tla.BrokenRules):
            tla.write(tmp_path / "piece.tla", doc)

    def test_a_change_to_a_component_not_involved_is_written(self, tmp_path):
        doc = tla.loads(a_file(CROSSING))
        doc.timelines[CADENCES].components[CADENCE].attrs["label"] = "HC"
        path = tmp_path / "piece.tla"
        tla.write(path, doc)
        read = tla.read(path)
        assert read.timelines[CADENCES].components[CADENCE].attrs["label"] == "HC"
        assert [w.place for w in read.warnings] == [component_place(FORM, FIRST)]

    def test_a_new_component_at_a_problems_place_is_a_new_problem(self, tmp_path):
        # Another hierarchy crossing the first: its problem isn't one read.
        doc = tla.loads(a_file(CROSSING))
        doc.timelines[FORM].components[THIRD] = tla.Component(
            id=THIRD, kind="hierarchy", attrs=at_level(1.5, 4.0, 1)
        )
        with pytest.raises(tla.BrokenRules) as refused:
            tla.write(tmp_path / "piece.tla", doc)
        messages = [w.message for w in refused.value.problems]
        assert len(messages) == 2
        assert component_place(FORM, THIRD) in messages[0]
        assert component_place(FORM, SECOND) not in messages[0]
        assert component_place(FORM, THIRD) in messages[1]

    def test_every_new_problem_is_listed(self, tmp_path):
        doc = tla.loads(a_file())
        doc.timelines[FORM].components[SECTION].attrs["level"] = 0
        doc.timelines[CADENCES].components[CADENCE].attrs["time"] = -1.0
        doc.timelines[CADENCES].components[CADENCE].attrs["color"] = "notacolor"
        with pytest.raises(tla.BrokenRules) as refused:
            tla.write(tmp_path / "piece.tla", doc)
        assert [w.message for w in refused.value.problems] == [
            "Level can't be below 1. Got '0'",
            "Time can't be negative. Got '-00:01.0'",
            "notacolor is not a valid color.",
        ]

    def test_once_fixed_it_writes_without_a_warning(self, tmp_path):
        doc = tla.loads(a_file(CROSSING))
        doc.timelines[FORM].components[SECOND].attrs["start"] = 2.0
        path = tmp_path / "piece.tla"
        tla.write(path, doc)
        assert tla.read(path).warnings == []

    def test_a_file_can_be_fixed_over_several_sessions(self, tmp_path):
        path = tmp_path / "piece.tla"
        path.write_bytes(
            a_file(
                together(
                    LEVEL_0,
                    markers((SECOND, {"time": 1.0}), (THIRD, {"time": 1.0})),
                )
            )
        )
        doc = tla.read(path)
        assert len(doc.warnings) == 2

        doc.timelines[CADENCES].components[THIRD].attrs["time"] = 2.0
        tla.write(path, doc)

        doc = tla.read(path)
        assert [w.place for w in doc.warnings] == [component_place(FORM, FIRST)]

        doc.timelines[FORM].components[FIRST].attrs["level"] = 1
        tla.write(path, doc)
        assert tla.read(path).warnings == []

    def test_taking_one_of_those_it_crosses_away_keeps_the_others(self, tmp_path):
        doc = tla.loads(
            a_file(
                hierarchies(
                    (FIRST, at_level(0.0, 2.0, 1)),
                    (SECOND, at_level(1.0, 3.0, 1)),
                    (THIRD, at_level(1.5, 4.0, 1)),
                )
            )
        )
        del doc.timelines[FORM].components[THIRD]
        path = tmp_path / "piece.tla"
        tla.write(path, doc)
        assert [w.place for w in tla.read(path).warnings] == [
            component_place(FORM, FIRST)
        ]

    def test_a_problem_fixed_and_written_cant_come_back(self, tmp_path):
        # The document follows the file: the file no longer has the problem.
        doc = tla.loads(a_file(LEVEL_0))
        attrs = doc.timelines[FORM].components[FIRST].attrs
        path = tmp_path / "piece.tla"
        attrs["level"] = 1
        tla.write(path, doc)
        attrs["level"] = 0
        with pytest.raises(tla.BrokenRules):
            tla.write(path, doc)

    def test_a_problem_set_back_as_it_was_read_is_written(self, tmp_path):
        data = a_file(LEVEL_0)
        doc = tla.loads(data)
        attrs = doc.timelines[FORM].components[FIRST].attrs
        attrs["level"] = 1
        attrs["level"] = 0
        path = tmp_path / "piece.tla"
        tla.write(path, doc)
        assert path.read_bytes() == data

    def test_a_media_length_that_puts_a_time_beyond_it_is_a_new_problem(self, tmp_path):
        doc = tla.loads(
            a_file(together(with_media_length(60.0), markers((FIRST, {"time": 30.0}))))
        )
        doc.media_length = 20.0
        with pytest.raises(tla.BrokenRules) as refused:
            tla.write(tmp_path / "piece.tla", doc)
        assert [w.place for w in refused.value.problems][0] == component_place(
            CADENCES, FIRST
        )

    def test_a_document_made_in_memory_has_nothing_read_to_keep(self, tmp_path):
        doc = tla.new_document()
        form = tla.new_id()
        component = tla.new_id()
        doc.timelines[form] = tla.Timeline(
            id=form,
            kind="hierarchy",
            ordinal=1,
            attrs={"height": 60},
            components={
                component: tla.Component(
                    id=component, kind="hierarchy", attrs=at_level(0.0, 2.0, 0)
                )
            },
        )
        path = tmp_path / "piece.tla"
        with pytest.raises(tla.BrokenRules) as refused:
            tla.write(path, doc)
        assert not path.exists()
        assert refused.value.problems[0].place == component_place(form, component)

        doc.timelines[form].components[component].attrs["level"] = 1
        tla.write(path, doc)
        assert tla.read(path).warnings == []

    def test_an_integer_given_as_a_float_is_checked_as_written(self, tmp_path):
        # FR-051a: it is written as an integer, which keeps to the rules.
        doc = tla.loads(a_file())
        doc.timelines[FORM].components[SECTION].attrs["level"] = 2.0
        path = tmp_path / "piece.tla"
        tla.write(path, doc)
        assert tla.read(path).timelines[FORM].components[SECTION].attrs["level"] == 2

    def test_a_problem_given_as_a_float_is_the_problem_read(self, tmp_path):
        data = a_file(LEVEL_0)
        doc = tla.loads(data)
        doc.timelines[FORM].components[FIRST].attrs["level"] = 0.0
        path = tmp_path / "piece.tla"
        tla.write(path, doc)
        assert path.read_bytes() == data

    def test_canonical_bytes_doesnt_refuse(self):
        doc = tla.loads(a_file(LEVEL_0))
        doc.timelines[FORM].components[FIRST].attrs["end"] = 3.0
        tla.canonical_bytes(doc)
        writer.checked_bytes(doc)
        tla.fingerprint_of(doc)

    def test_copies_of_a_document_keep_what_was_read(self, tmp_path):
        data = a_file(LEVEL_0)
        doc = tla.loads(data)
        for copied in (copy.deepcopy(doc), dataclasses.replace(doc)):
            path = tmp_path / "piece.tla"
            tla.write(path, copied)
            assert path.read_bytes() == data


class TestBrokenRules:
    def refused(self, tmp_path):
        doc = tla.loads(a_file())
        doc.timelines[FORM].components[SECTION].attrs["level"] = 0
        doc.timelines[CADENCES].components[CADENCE].attrs["color"] = "re\ud83d"
        with pytest.raises(tla.BrokenRules) as refused:
            tla.write(tmp_path / "piece.tla", doc)
        return refused.value

    def test_it_is_a_value_error(self, tmp_path):
        assert isinstance(self.refused(tmp_path), ValueError)

    def test_it_reads_as_a_sentence_naming_each_problem(self, tmp_path):
        error = self.refused(tmp_path)
        lines = [problem.line for problem in error.problems]
        assert str(error) == (
            "piece.tla: nothing was written, it breaks the rules for a valid"
            f" component: line {lines[0]}: Level can't be below 1. Got '0';"
            f" line {lines[1]}: re\\ud83d is not a valid color."
        )
        str(error).encode("utf-8")

    def test_it_can_be_copied_and_pickled(self, tmp_path):
        error = self.refused(tmp_path)
        for again in (copy.copy(error), pickle.loads(pickle.dumps(error))):
            assert isinstance(again, tla.BrokenRules)
            assert again.path == error.path
            assert again.problems == error.problems
            assert str(again) == str(error)


# Without the `harmony` extra


KEYS = harmony_timeline((FIRST, harmony(1.0)), (SECOND, mode(2.0)))


class TestWithoutMusic21:
    def test_a_file_with_harmonies_reads_with_one_note(self, without_music21):
        doc = tla.loads(a_file(KEYS))
        assert doc.warnings == [
            tla.ReadWarning(
                place="",
                line=None,
                message="a harmony's quality and inversion and a mode's type weren't"
                f" checked: checking a harmony needs: {INSTALL}",
            )
        ]
        assert doc.read_problems == []

    def test_its_other_checks_are_made(self, without_music21):
        data = a_file(
            harmony_timeline(
                (FIRST, harmony(-1.0)),
                (SECOND, harmony(1.0, step=9)),
                (THIRD, harmony(2.0)),
                (FOURTH, harmony(2.0)),
            )
        )
        messages = [w.message for w in tla.loads(data).warnings]
        assert messages[:-1] == [
            "Time can't be negative. Got '-00:01.0'",
            "9 is not a valid step.",
            "There is already a harmony component at the selected position."
            f" {named(data, FOURTH, timeline=HARMONIES)}",
        ]
        assert INSTALL in messages[-1]

    def test_the_note_is_given_when_every_harmony_breaks_another_rule(
        self, without_music21
    ):
        doc = tla.loads(a_file(harmony_timeline((FIRST, harmony(-1.0)))))
        assert INSTALL in doc.warnings[-1].message
        assert len(doc.warnings) == 2

    def test_a_file_with_only_modes_names_a_mode(self, without_music21):
        doc = tla.loads(a_file(harmony_timeline((FIRST, mode(1.0)))))
        assert f"checking a mode needs: {INSTALL}" in doc.warnings[0].message

    def test_a_file_without_harmonies_has_no_note(self, without_music21):
        assert tla.loads(a_file()).warnings == []

    def test_an_empty_harmony_timeline_has_no_note(self, without_music21):
        assert tla.loads(a_file(harmony_timeline())).warnings == []

    def test_a_harmony_of_a_kind_its_timeline_doesnt_hold_has_no_note(
        self, without_music21
    ):
        # Kept as it is, not as a harmony.
        def change(content):
            content["timelines"][CADENCES]["components"][FIRST] = harmony(1.0)

        messages = [w.message for w in tla.loads(a_file(change)).warnings]
        assert not any(INSTALL in message for message in messages)

    def test_writing_it_is_refused_naming_the_command(self, without_music21, tmp_path):
        path = tmp_path / "piece.tla"
        doc = tla.loads(a_file(KEYS))
        with pytest.raises(tla.BrokenRules) as refused:
            tla.write(path, doc)
        assert not path.exists()
        assert refused.value.problems == [
            tla.ReadWarning(
                place="",
                line=None,
                message=f"checking a harmony needs: {INSTALL}",
            )
        ]
        assert INSTALL in str(refused.value)

    def test_writing_it_is_refused_when_every_harmony_breaks_another_rule(
        self, without_music21, tmp_path
    ):
        path = tmp_path / "piece.tla"
        doc = tla.loads(a_file(harmony_timeline((FIRST, harmony(-1.0)))))
        with pytest.raises(tla.BrokenRules) as refused:
            tla.write(path, doc)
        assert not path.exists()
        assert INSTALL in str(refused.value)

    def test_a_new_problem_is_listed_with_the_command(self, without_music21, tmp_path):
        doc = tla.loads(a_file(KEYS))
        doc.timelines[FORM].components[SECTION].attrs["level"] = 0
        with pytest.raises(tla.BrokenRules) as refused:
            tla.write(tmp_path / "piece.tla", doc)
        assert [w.message for w in refused.value.problems] == [
            "Level can't be below 1. Got '0'",
            f"checking a harmony needs: {INSTALL}",
        ]

    def test_a_document_without_harmonies_is_written(self, without_music21, tmp_path):
        data = a_file(LEVEL_0)
        path = tmp_path / "piece.tla"
        tla.write(path, tla.loads(data))
        assert path.read_bytes() == data

    def test_a_music21_that_wont_import_gives_the_reason(self, monkeypatch, tmp_path):
        find_spec = importlib.util.find_spec

        def found(name, *args, **kwargs):
            if name.partition(".")[0] == "music21":
                return object()
            return find_spec(name, *args, **kwargs)

        monkeypatch.setattr(importlib.util, "find_spec", found)
        for name in ("music21", "music21.harmony", "music21.key"):
            monkeypatch.setitem(sys.modules, name, None)
        doc = tla.loads(a_file(KEYS))
        assert "can't be imported" in doc.warnings[0].message
        assert INSTALL in doc.warnings[0].message
        with pytest.raises(tla.BrokenRules, match="can't be imported"):
            tla.write(tmp_path / "piece.tla", doc)


class TestWithMusic21:
    def test_a_quality_that_isnt_one_is_warned_about_and_written_back(
        self, music21, tmp_path
    ):
        data = a_file(harmony_timeline((FIRST, harmony(1.0, quality="made-up"))))
        doc = tla.loads(data)
        assert [w.message for w in doc.warnings] == ["made-up is not a valid quality."]
        path = tmp_path / "piece.tla"
        tla.write(path, doc)
        assert path.read_bytes() == data

    def test_a_new_quality_that_isnt_one_is_refused(self, music21, tmp_path):
        doc = tla.loads(a_file(harmony_timeline((FIRST, harmony(1.0)))))
        doc.timelines[HARMONIES].components[FIRST].attrs["quality"] = "made-up"
        with pytest.raises(tla.BrokenRules):
            tla.write(tmp_path / "piece.tla", doc)

    def test_a_file_with_harmonies_is_written(self, music21, tmp_path):
        data = a_file(harmony_timeline((FIRST, harmony(1.0)), (SECOND, mode(1.0))))
        path = tmp_path / "piece.tla"
        tla.write(path, tla.loads(data))
        assert path.read_bytes() == data


# Old files


def old_file(*hierarchy_attrs):
    """A TiLiA 0.6 file with one hierarchy timeline holding these hierarchies,
    with ids 17 on, and the timeline's id 3."""
    return json.dumps(
        {
            "file_path": "",
            "media_path": "",
            "media_metadata": {"media length": 60.0},
            "timelines": {
                "3": {
                    "kind": "Hierarchy",
                    "name": "Form",
                    "ordinal": 1,
                    "height": 30,
                    "is_visible": True,
                    "components": {
                        str(17 + n): {"kind": "HIERARCHY", "hash": "0e1f", **attrs}
                        for n, attrs in enumerate(hierarchy_attrs)
                    },
                }
            },
            "app_name": "TiLiA",
            "version": "0.6.0",
        },
        indent=2,
    ).encode("utf-8")


class TestOldFiles:
    def test_a_problem_is_named_in_the_old_files_terms(self):
        data = old_file({"start": 0.0, "end": 2.0, "level": 0})
        assert tla.loads(data).warnings == [
            tla.ReadWarning(
                place="/timelines/3/components/17",
                line=line_of(data, "17"),
                message="Level can't be below 1. Got '0'",
            )
        ]

    def test_the_other_component_is_named_in_the_old_files_terms(self):
        data = old_file(
            {"start": 0.0, "end": 2.0, "level": 1},
            {"start": 1.0, "end": 3.0, "level": 1},
        )
        warnings = tla.loads(data).warnings
        assert len(warnings) == 1
        place = warnings[0].place
        other = "18" if place.endswith("/17") else "17"
        assert warnings[0].message == (
            f"{OVERLAP} (other component: line {line_of(data, other)},"
            f" /timelines/3/components/{other})"
        )

    def test_it_migrates_with_its_problem(self, tmp_path):
        data = old_file({"start": 0.0, "end": 2.0, "level": 0})
        path = tmp_path / "piece.tla"
        path.write_bytes(data)
        doc = tla.read(path)
        tla.write(path, doc, expect=tla.fingerprint(path))
        migrated = tla.read(path)
        component = next(iter(next(iter(migrated.timelines.values())).components))
        timeline = next(iter(migrated.timelines))
        assert [(w.place, w.message) for w in migrated.warnings] == [
            (
                component_place(timeline, component),
                "Level can't be below 1. Got '0'",
            )
        ]
        assert path.read_bytes() == tla.canonical_bytes(migrated)

    def test_a_change_to_a_component_with_a_problem_is_refused(self, tmp_path):
        doc = tla.loads(old_file({"start": 0.0, "end": 2.0, "level": 0}))
        timeline = next(iter(doc.timelines.values()))
        next(iter(timeline.components.values())).attrs["label"] = "A"
        with pytest.raises(tla.BrokenRules):
            tla.write(tmp_path / "piece.tla", doc)

    @pytest.mark.parametrize("path", sorted(OLD.glob("*.tla")), ids=lambda p: p.name)
    def test_each_old_version_migrates_with_the_problems_it_has(
        self, path, tmp_path, music21
    ):
        doc = tla.read(path)
        found = len(doc.read_problems)
        written = tmp_path / path.name
        tla.write(written, doc)
        again = tla.read(written)
        assert len(again.read_problems) == found
        data = written.read_bytes()
        tla.write(written, again)
        assert written.read_bytes() == data

    @pytest.mark.skipif(
        not hasattr(tla, "migrate_folder"),
        reason="needs tilia migrate, TimeLineAnnotator/project-management#183",
    )
    def test_its_warning_is_in_tilia_migrates_report(self, tmp_path):
        data = old_file({"start": 0.0, "end": 2.0, "level": 0})
        (tmp_path / "piece.tla").write_bytes(data)
        report = tla.migrate_folder(tmp_path, apply=True)
        assert report.files[0].outcome == "migrated"
        assert [w.message for w in report.files[0].warnings] == [
            "Level can't be below 1. Got '0'"
        ]


@pytest.mark.parametrize("path", sorted(GOLDEN.glob("*.tla")), ids=lambda p: p.name)
def test_the_golden_files_keep_to_the_rules(path, music21):
    assert tla.read(path).read_problems == []


def test_the_reader_finds_what_the_rules_find():
    # The reader adds no rule of its own: what it warns about is what the
    # rules give for the same component.
    outcome = rules.hierarchy(float("inf"), (), at_level(0.0, 2.0, 0))
    assert [w.message for w in tla.loads(a_file(LEVEL_0)).warnings] == [outcome.reason]
