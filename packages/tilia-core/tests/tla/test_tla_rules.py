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
BEAT_1, BEAT_2 = IDS["beat_1"], IDS["beat_2"]
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

    def test_a_row_with_only_a_bad_color_has_one_warning(self):
        def change(content):
            content["timelines"][TEXTURE]["rows"].append(dict(BASS))

        doc = tla.loads(a_file(change))
        assert [w.message for w in doc.warnings] == ["notacolor is not a valid color."]
        assert len(doc.read_problems) == 1

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

    def test_written_to_another_folder_its_problems_are_written_back(self, tmp_path):
        # Its paths are rebased (FR-033), which changes no component.
        def change(content):
            LEVEL_0(content)
            content["media"]["path"] = "piece.mp3"

        here = tmp_path / "here" / "piece.tla"
        here.parent.mkdir()
        here.write_bytes(a_file(change))
        there = tmp_path / "there" / "piece.tla"
        there.parent.mkdir()
        doc = tla.read(here)
        tla.write(there, doc)
        assert doc.media_path == "../here/piece.mp3"
        assert [w.message for w in tla.read(there).warnings] == [
            "Level can't be below 1. Got '0'"
        ]

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


# What counts as a new problem: what is wrong, not how it reads (FR-054;
# TimeLineAnnotator/project-management#494). In the first class the component
# with the problem isn't touched, whatever a reason quotes or a place was.

BASS = {"id": "bbbbbb", "name": "Bass", "color": "notacolor"}
TUNE = {"id": "cccccc", "name": "Tune"}


def ranges(*components, rows=None):
    """A change: the Texture timeline holds these ranges, given as (id,
    attributes), on the row `ROW` unless they say otherwise, and has `rows`."""

    def change(content):
        timeline = content["timelines"][TEXTURE]
        timeline["components"] = {
            key: {"kind": "RANGE", "row_id": ROW, **attrs} for key, attrs in components
        }
        if rows is not None:
            timeline["rows"] = copy.deepcopy(rows)

    return change


def a_range(start, end, **attrs):
    return {"start": start, "end": end, **attrs}


def beats(*components):
    def change(content):
        content["timelines"][BEATS]["components"].update(
            {key: {"kind": "BEAT", **attrs} for key, attrs in components}
        )

    return change


def written(doc, tmp_path):
    path = tmp_path / "piece.tla"
    tla.write(path, doc)
    return path


def refused(doc, tmp_path):
    """The problems `write` refuses `doc` for, and nothing written."""
    path = tmp_path / "piece.tla"
    with pytest.raises(tla.BrokenRules) as error:
        tla.write(path, doc)
    assert not path.exists()
    return error.value.problems


PAST_THE_END = {
    "marker": (CADENCES, markers((FIRST, {"time": 150.0}))),
    "beat": (BEATS, beats((FIRST, {"time": 150.0}))),
    "hierarchy": (FORM, hierarchies((FIRST, at_level(140.0, 150.0, 1)))),
    "range": (TEXTURE, ranges((FIRST, a_range(140.0, 150.0)))),
}
A_MARKER_PAST_THE_END = together(with_media_length(100.0), PAST_THE_END["marker"][1])
A_GROUP = [make_id(300 + n) for n in range(20)]


def a_group(size):
    """A change: `size` markers at one time, in id order."""
    return markers(*((key, {"time": 5.0}) for key in A_GROUP[:size]))


class TestAnEditElsewhereIsNoNewProblem:
    def test_a_timeline_renamed_keeps_its_beat_pattern(self, tmp_path):
        doc = tla.loads(a_file(TestBeatPattern.with_pattern("x y")))
        doc.timelines[BEATS].name = "Renamed"
        read = tla.read(written(doc, tmp_path))
        assert read.timelines[BEATS].name == "Renamed"
        assert read.timelines[BEATS].attrs["beat_pattern"] == "x y"
        assert [w.message for w in read.warnings] == [
            'the beat pattern "x y" of the timeline "Renamed" isn\'t a valid pattern'
        ]

    @pytest.mark.parametrize(
        "edit",
        [
            lambda rows: rows.insert(0, dict(TUNE)),
            lambda rows: rows.pop(0),
            lambda rows: rows.reverse(),
        ],
        ids=["a good row inserted first", "row 0 deleted", "the rows reversed"],
    )
    def test_a_row_keeps_its_problem_wherever_it_moves(self, edit, tmp_path):
        rows = [{"id": ROW, "name": "Melody"}, BASS]
        doc = tla.loads(a_file(ranges(rows=rows)))
        assert [w.place for w in doc.warnings] == [f"/timelines/{TEXTURE}/rows/1"]
        kept = doc.timelines[TEXTURE].attrs["rows"]
        edit(kept)
        read = tla.read(written(doc, tmp_path))
        index = [row["id"] for row in kept].index(BASS["id"])
        assert [(w.place, w.message) for w in read.warnings] == [
            (f"/timelines/{TEXTURE}/rows/{index}", "notacolor is not a valid color.")
        ]

    def test_a_range_between_a_join_can_be_deleted(self, tmp_path):
        doc = tla.loads(
            a_file(
                ranges(
                    (FIRST, a_range(0.0, 1.0, joined_right=THIRD)),
                    (SECOND, a_range(3.0, 3.5)),
                    (THIRD, a_range(5.0, 6.0)),
                )
            )
        )
        assert SECOND in doc.warnings[0].message
        del doc.timelines[TEXTURE].components[SECOND]
        read = tla.read(written(doc, tmp_path))
        assert [w.place for w in read.warnings] == [component_place(TEXTURE, FIRST)]
        assert "starts at 5.0" in read.warnings[0].message

    def test_a_range_between_a_join_can_change(self, tmp_path):
        # The problem is between the range and the one it joins. What the
        # reason quotes of the next range is how it reads.
        doc = tla.loads(
            a_file(
                ranges(
                    (FIRST, a_range(0.0, 1.0, joined_right=THIRD)),
                    (SECOND, a_range(3.0, 3.5)),
                    (THIRD, a_range(5.0, 6.0)),
                )
            )
        )
        doc.timelines[TEXTURE].components[SECOND].attrs["start"] = 3.2
        written(doc, tmp_path)

    def test_a_good_range_can_be_added_after_a_backward_join(self, tmp_path):
        doc = tla.loads(
            a_file(
                ranges(
                    (FIRST, a_range(0.0, 1.0)),
                    (SECOND, a_range(5.0, 6.0, joined_right=FIRST)),
                )
            )
        )
        assert "last range of row" in doc.warnings[0].message
        doc.timelines[TEXTURE].components[THIRD] = tla.Component(
            id=THIRD, kind="range", attrs={**a_range(8.0, 9.0), "row_id": ROW}
        )
        read = tla.read(written(doc, tmp_path))
        assert [w.place for w in read.warnings] == [component_place(TEXTURE, SECOND)]
        assert "starts at 8.0" in read.warnings[0].message

    def test_a_row_renamed_keeps_a_join_on_it(self, tmp_path):
        doc = tla.loads(
            a_file(
                ranges(
                    (FIRST, a_range(0.0, 1.0, joined_right=SECOND)),
                    (SECOND, a_range(3.0, 4.0)),
                )
            )
        )
        assert "row 'Melody'" in doc.warnings[0].message
        doc.timelines[TEXTURE].attrs["rows"][0]["name"] = "Tune"
        read = tla.read(written(doc, tmp_path))
        assert "row 'Tune'" in read.warnings[0].message

    @pytest.mark.parametrize("kind", PAST_THE_END)
    @pytest.mark.parametrize("length", [120.0, 130.5, 90.0, 100.01])
    def test_a_time_past_the_end_stays_with_a_new_length(self, kind, length, tmp_path):
        timeline, change = PAST_THE_END[kind]
        doc = tla.loads(a_file(together(with_media_length(100.0), change)))
        assert len(doc.warnings) == 1
        doc.media_length = length
        read = tla.read(written(doc, tmp_path))
        assert read.media_length == length
        assert [w.place for w in read.warnings] == [component_place(timeline, FIRST)]

    def test_a_length_past_it_fixes_the_problem(self, tmp_path):
        doc = tla.loads(a_file(A_MARKER_PAST_THE_END))
        doc.media_length = 200.0
        assert tla.read(written(doc, tmp_path)).warnings == []

    def test_a_hierarchy_past_the_end_by_its_start_or_its_end_is_one_problem(
        self, tmp_path
    ):
        # At 100 its end is past it, and at 85 its start, which the reasons say.
        doc = tla.loads(
            a_file(
                together(
                    with_media_length(100.0),
                    hierarchies((FIRST, at_level(90.0, 110.0, 1))),
                )
            )
        )
        assert doc.warnings[0].message.startswith("End time")
        doc.media_length = 85.0
        read = tla.read(written(doc, tmp_path))
        assert read.warnings[0].message.startswith("Start time")

    @pytest.mark.parametrize("kind", PAST_THE_END)
    def test_a_length_first_learned_is_no_new_problem(self, kind, tmp_path):
        # With no length, a time isn't compared with any: it had this problem
        # all along, for all the reader could tell.
        timeline, change = PAST_THE_END[kind]
        doc = tla.loads(a_file(change))
        assert doc.warnings == []
        doc.media_length = 100.0
        read = tla.read(written(doc, tmp_path))
        assert [w.place for w in read.warnings] == [component_place(timeline, FIRST)]

    def test_a_length_first_learned_after_a_write_is_no_new_problem(self, tmp_path):
        doc = tla.loads(a_file(PAST_THE_END["marker"][1]))
        written(doc, tmp_path)
        doc.media_length = 100.0
        written(doc, tmp_path)

    @pytest.mark.parametrize("size", [11, 12, 13, 20])
    def test_any_of_a_group_at_one_time_can_be_deleted(self, size, tmp_path):
        data = a_file(a_group(size))
        for gone in A_GROUP[:size]:
            doc = tla.loads(data)
            del doc.timelines[CADENCES].components[gone]
            written(doc, tmp_path)

    @pytest.mark.parametrize("size", [11, 12, 13, 20])
    def test_any_of_a_group_at_one_time_can_be_moved_away(self, size, tmp_path):
        data = a_file(a_group(size))
        for moved in A_GROUP[:size]:
            doc = tla.loads(data)
            doc.timelines[CADENCES].components[moved].attrs["time"] = 7.0
            written(doc, tmp_path)

    def test_several_of_a_group_can_be_deleted_over_several_sessions(self, tmp_path):
        doc = tla.loads(a_file(a_group(13)))
        for gone in A_GROUP[:11]:
            del doc.timelines[CADENCES].components[gone]
            written(doc, tmp_path)
        assert len(tla.read(tmp_path / "piece.tla").warnings) == 1

    def test_a_warning_still_names_ten_others_at_most(self):
        first = tla.loads(a_file(a_group(13))).warnings[0].message
        assert first.endswith("; and 2 more)")
        assert first.count("/components/") == 10


class TestStillANewProblem:
    @pytest.mark.parametrize(
        "attrs, message",
        [
            ({"time": -1.0}, "Time can't be negative. Got '-00:01.0'"),
            ({"time": 150.0}, "Time '02:30.0' is bigger than media time '01:40.0'"),
            ({"time": 5.0, "color": "bad"}, "bad is not a valid color."),
        ],
    )
    def test_a_new_problem_on_a_new_component(self, attrs, message, tmp_path):
        doc = tla.loads(a_file(with_media_length(100.0)))
        doc.timelines[CADENCES].components[FIRST] = tla.Component(
            id=FIRST, kind="marker", attrs=attrs
        )
        problems = refused(doc, tmp_path)
        assert [(w.place, w.message) for w in problems] == [
            (component_place(CADENCES, FIRST), message)
        ]

    def test_a_new_component_past_a_length_first_learned(self, tmp_path):
        doc = tla.loads(a_file())
        doc.media_length = 100.0
        doc.timelines[CADENCES].components[FIRST] = tla.Component(
            id=FIRST, kind="marker", attrs={"time": 150.0}
        )
        assert [w.place for w in refused(doc, tmp_path)] == [
            component_place(CADENCES, FIRST)
        ]

    def test_a_new_component_past_the_end_beside_one_read_past_it(self, tmp_path):
        doc = tla.loads(a_file(A_MARKER_PAST_THE_END))
        doc.timelines[CADENCES].components[SECOND] = tla.Component(
            id=SECOND, kind="marker", attrs={"time": 160.0}
        )
        assert [w.place for w in refused(doc, tmp_path)] == [
            component_place(CADENCES, SECOND)
        ]

    def test_a_new_component_in_a_group_at_one_time(self, tmp_path):
        doc = tla.loads(a_file(a_group(13)))
        doc.timelines[CADENCES].components[FIRST] = tla.Component(
            id=FIRST, kind="marker", attrs={"time": 5.0}
        )
        assert refused(doc, tmp_path)

    def test_a_beat_moved_onto_another(self, tmp_path):
        doc = tla.loads(a_file())
        assert doc.read_problems == []
        doc.timelines[BEATS].components[BEAT_2].attrs["time"] = 0.0
        problems = refused(doc, tmp_path)
        assert [w.place for w in problems] == [component_place(BEATS, BEAT_1)]
        assert problems[0].message.startswith(
            "There is already a beat component at the selected position."
        )

    def test_a_marker_moved_onto_one_of_two_at_one_time(self, tmp_path):
        doc = tla.loads(
            a_file(
                markers(
                    (FIRST, {"time": 1.0}),
                    (SECOND, {"time": 1.0}),
                    (THIRD, {"time": 2.0}),
                )
            )
        )
        doc.timelines[CADENCES].components[THIRD].attrs["time"] = 1.0
        message = refused(doc, tmp_path)[0].message
        assert component_place(CADENCES, THIRD) in message
        assert component_place(CADENCES, SECOND) not in message

    def test_a_component_changed_breaks_a_rule_it_didnt_break(self, tmp_path):
        doc = tla.loads(a_file())
        doc.timelines[CADENCES].components[CADENCE].attrs["time"] = -1.0
        assert [w.message for w in refused(doc, tmp_path)] == [
            "Time can't be negative. Got '-00:01.0'"
        ]

    def test_a_component_with_a_problem_changed_breaks_another_rule(self, tmp_path):
        doc = tla.loads(a_file(LEVEL_0))
        doc.timelines[FORM].components[FIRST].attrs["end"] = -1.0
        assert "End time '-1.0' should be bigger than start time '0.0'" in [
            w.message for w in refused(doc, tmp_path)
        ]

    def test_a_component_with_a_problem_changed_keeps_it(self, tmp_path):
        # FR-054, until tla.keep_read_problems comes:
        # TimeLineAnnotator/project-management#439.
        doc = tla.loads(a_file(A_MARKER_PAST_THE_END))
        doc.timelines[CADENCES].components[FIRST].attrs["label"] = "A"
        assert [w.place for w in refused(doc, tmp_path)] == [
            component_place(CADENCES, FIRST)
        ]

    def test_a_component_changed_past_a_new_length(self, tmp_path):
        doc = tla.loads(a_file(A_MARKER_PAST_THE_END))
        doc.media_length = 120.0
        doc.timelines[CADENCES].components[FIRST].attrs["label"] = "A"
        assert refused(doc, tmp_path)

    @pytest.mark.parametrize(
        "edit",
        [lambda attrs: attrs.update(time=160.0), lambda attrs: attrs.update(label="A")],
        ids=["moved", "labelled"],
    )
    def test_a_component_changed_past_a_length_first_learned(self, edit, tmp_path):
        doc = tla.loads(a_file(markers((FIRST, {"time": 150.0}))))
        doc.media_length = 100.0
        edit(doc.timelines[CADENCES].components[FIRST].attrs)
        assert [w.place for w in refused(doc, tmp_path)] == [
            component_place(CADENCES, FIRST)
        ]

    def test_a_range_joined_to_one_that_moved(self, tmp_path):
        doc = tla.loads(
            a_file(
                ranges(
                    (FIRST, a_range(0.0, 1.0, joined_right=SECOND)),
                    (SECOND, a_range(3.0, 4.0)),
                )
            )
        )
        doc.timelines[TEXTURE].components[SECOND].attrs["start"] = 3.5
        problems = refused(doc, tmp_path)
        assert [w.place for w in problems] == [component_place(TEXTURE, FIRST)]
        assert "starts at 3.5" in problems[0].message

    def test_a_range_joined_to_one_that_changed(self, tmp_path):
        doc = tla.loads(
            a_file(
                ranges(
                    (FIRST, a_range(0.0, 1.0, joined_right=THIRD)),
                    (SECOND, a_range(3.0, 3.5)),
                    (THIRD, a_range(5.0, 6.0)),
                )
            )
        )
        doc.timelines[TEXTURE].components[THIRD].attrs["label"] = "A"
        problems = refused(doc, tmp_path)
        assert [w.place for w in problems] == [component_place(TEXTURE, FIRST)]
        # As the rule names them: what comes next in its row.
        assert component_place(TEXTURE, SECOND) in problems[0].message
        assert component_place(TEXTURE, THIRD) not in problems[0].message

    def test_an_unchanged_component_breaks_a_rule_it_wasnt_read_with(self, tmp_path):
        # Its color is what it was read with. Its join is new, for a range added
        # before the next.
        doc = tla.loads(
            a_file(
                ranges(
                    (FIRST, a_range(0.0, 1.0, joined_right=THIRD, color="notacolor")),
                    (THIRD, a_range(1.0, 2.0)),
                )
            )
        )
        assert len(doc.read_problems) == 1
        doc.timelines[TEXTURE].components[SECOND] = tla.Component(
            id=SECOND, kind="range", attrs={**a_range(0.5, 0.7), "row_id": ROW}
        )
        problems = refused(doc, tmp_path)
        assert [w.place for w in problems] == [component_place(TEXTURE, FIRST)]
        assert problems[0].message.startswith("joined_with_next=true")

    def test_a_range_added_before_the_next_breaks_a_join_read_whole(self, tmp_path):
        doc = tla.loads(a_file())
        doc.timelines[TEXTURE].components[FIRST] = tla.Component(
            id=FIRST, kind="range", attrs={**a_range(0.5, 0.7), "row_id": ROW}
        )
        assert [w.place for w in refused(doc, tmp_path)] == [
            component_place(TEXTURE, MELODY_1)
        ]

    def test_two_at_one_time_both_moved_to_another(self, tmp_path):
        doc = tla.loads(
            a_file(markers((FIRST, {"time": 1.0}), (SECOND, {"time": 1.0})))
        )
        components = doc.timelines[CADENCES].components
        components[FIRST].attrs["time"] = components[SECOND].attrs["time"] = 2.0
        assert [w.place for w in refused(doc, tmp_path)] == [
            component_place(CADENCES, FIRST)
        ]

    def test_two_that_cross_and_one_changed_to_lie_at_the_same_place(self, tmp_path):
        doc = tla.loads(a_file(CROSSING))
        attrs = doc.timelines[FORM].components[SECOND].attrs
        attrs["start"], attrs["end"] = 0.0, 2.0
        messages = [w.message for w in refused(doc, tmp_path)]
        assert any(
            message.startswith("There is already a hierarchy component")
            for message in messages
        )

    def test_a_kind_changed_and_all_else_the_same(self, music21, tmp_path):
        doc = tla.loads(a_file(harmony_timeline((FIRST, harmony(-1.0)))))
        assert len(doc.read_problems) == 1
        doc.timelines[HARMONIES].components[FIRST] = tla.Component(
            id=FIRST, kind="mode", attrs={"time": -1.0}
        )
        assert [w.place for w in refused(doc, tmp_path)] == [
            component_place(HARMONIES, FIRST)
        ]

    def test_a_row_with_a_problem_changed(self, tmp_path):
        doc = tla.loads(a_file(ranges(rows=[{"id": ROW, "name": "Melody"}, BASS])))
        doc.timelines[TEXTURE].attrs["rows"][1]["name"] = "Low"
        assert [w.message for w in refused(doc, tmp_path)] == [
            "notacolor is not a valid color."
        ]

    def test_a_new_row_with_a_problem(self, tmp_path):
        doc = tla.loads(a_file())
        doc.timelines[TEXTURE].attrs["rows"].append(dict(BASS))
        assert [w.place for w in refused(doc, tmp_path)] == [
            f"/timelines/{TEXTURE}/rows/1"
        ]

    def test_a_refused_row_is_named_where_it_is_now(self, tmp_path):
        doc = tla.loads(a_file())
        doc.timelines[TEXTURE].attrs["rows"].insert(0, dict(BASS))
        assert [w.place for w in refused(doc, tmp_path)] == [
            f"/timelines/{TEXTURE}/rows/0"
        ]


class TestWithNoLengthRead:
    """Every component's state is kept for a length given later, but only then."""

    def test_each_component_the_rules_cover_is_kept(self):
        def change(content):
            content["timelines"][CADENCES]["components"][FIRST] = {"kind": "FUTURE"}

        kept = tla.loads(a_file(change)).read_unmeasured
        assert component_place(CADENCES, CADENCE) in kept
        assert component_place(BEATS, BEAT_1) in kept
        assert component_place(CADENCES, FIRST) not in kept

    def test_none_is_kept_with_a_length(self):
        assert tla.loads(a_file(with_media_length(100.0))).read_unmeasured == {}

    def test_none_is_kept_in_quarters(self):
        def change(content):
            content["time_unit"] = "quarters"

        assert tla.loads(a_file(change)).read_unmeasured == {}

    def test_none_is_kept_once_it_is_written_with_a_length(self, tmp_path):
        doc = tla.loads(a_file())
        assert doc.read_unmeasured != {}
        doc.media_length = 100.0
        written(doc, tmp_path)
        assert doc.read_unmeasured == {}

    def test_what_is_kept_follows_the_file_while_it_has_no_length(self, tmp_path):
        doc = tla.loads(a_file(markers((FIRST, {"time": 1.5}))))
        doc.timelines[CADENCES].components[FIRST].attrs["time"] = 150.0
        written(doc, tmp_path)
        doc.media_length = 100.0
        written(doc, tmp_path)


class TestWhatIsComparedIsWhatIsWritten:
    """What the writer leaves out of what it writes isn't a change."""

    @pytest.mark.parametrize(
        "mark",
        [
            {"metadata": {}},
            {"metadata": {}, "force_display": False, "source": None},
            {"metadata": None},
            {"force_display": False},
        ],
    )
    @pytest.mark.parametrize(
        "time", [150.0, 1.0], ids=["past the end", "with another at one time"]
    )
    def test_a_measure_mark_with_what_is_left_out(self, mark, time, tmp_path):
        def change(content):
            content["media"]["length"] = 100.0
            content["timelines"][BEATS]["components"][FIRST] = {
                "kind": "BEAT",
                "time": time,
                "measure": mark,
            }

        doc = tla.loads(a_file(change))
        assert len(doc.read_problems) == 1
        again = tla.read(written(doc, tmp_path))
        assert len(again.read_problems) == 1
        written(again, tmp_path)

    def test_a_row_with_what_is_left_out(self, tmp_path):
        rows = [{"id": ROW, "name": "Melody"}, {**BASS, "height": None}]
        doc = tla.loads(a_file(ranges(rows=rows)))
        assert len(doc.read_problems) == 1
        written(doc, tmp_path)

    def test_an_empty_mark_on_the_other_of_two_at_one_time(self, tmp_path):
        def change(content):
            components = content["timelines"][BEATS]["components"]
            components[BEAT_1]["measure"] = {"metadata": {}}
            components[BEAT_2]["time"] = 0.0

        written(tla.loads(a_file(change)), tmp_path)

    def test_with_no_length_it_is_compared_as_written_too(self, tmp_path):
        def change(content):
            content["timelines"][BEATS]["components"][FIRST] = {
                "kind": "BEAT",
                "time": 150.0,
                "measure": {"metadata": {}},
            }

        doc = tla.loads(a_file(change))
        doc.media_length = 100.0
        written(doc, tmp_path)


class TestAKnownKindInAnotherTimeline:
    # What the reader makes of it, as FR-054 asks of what is written: kept key
    # for key, as one of a kind the core doesn't know, to which no rule applies.

    @staticmethod
    def wrong_kind():
        doc = tla.loads(a_file())
        doc.timelines[CADENCES].components[FIRST] = tla.Component(
            id=FIRST, kind="hierarchy", attrs={"start": 5.0, "end": 1.0, "level": 0}
        )
        return doc

    def test_it_is_written_and_reads_back_kept_as_it_is(self, tmp_path):
        read = tla.read(written(self.wrong_kind(), tmp_path))
        kept = read.timelines[CADENCES].components[FIRST]
        assert kept.kind == tla.UnknownKind("HIERARCHY")
        assert kept.extra == {"start": 5.0, "end": 1.0, "level": 0}
        assert read.read_problems == []
        assert [w.place for w in read.warnings] == [component_place(CADENCES, FIRST)]
        assert "it is kept as it is" in read.warnings[0].message

    def test_it_is_written_back_key_for_key(self, tmp_path):
        path = written(self.wrong_kind(), tmp_path)
        content = json.loads(path.read_bytes())
        assert content["timelines"][CADENCES]["components"][FIRST] == {
            "kind": "HIERARCHY",
            "start": 5.0,
            "end": 1.0,
            "level": 0,
        }
        tla.write(path, tla.read(path))
        data = path.read_bytes()
        assert json.loads(data) == content
        tla.write(path, tla.read(path))
        assert path.read_bytes() == data


class TestAFailedWrite:
    """What was read stays what was read until the file is written."""

    @staticmethod
    def fixed():
        # Its problems are no longer those of what would be written.
        doc = tla.loads(a_file(LEVEL_0))
        del doc.timelines[FORM].components[FIRST]
        return doc

    def test_a_file_that_changed_leaves_the_problems_read(self, tmp_path):
        doc = self.fixed()
        kept = list(doc.read_problems)
        assert kept != []
        path = tmp_path / "piece.tla"
        path.write_bytes(a_file())
        with pytest.raises(tla.FileChanged):
            tla.write(path, doc, expect="0" * 64)
        assert doc.read_problems == kept

    def test_a_folder_in_the_way_leaves_the_problems_read(self, tmp_path):
        doc = self.fixed()
        kept = list(doc.read_problems)
        with pytest.raises(IsADirectoryError):
            tla.write(tmp_path, doc)
        assert doc.read_problems == kept

    def test_a_failed_write_can_be_set_back_and_written(self, tmp_path):
        doc = tla.loads(a_file(LEVEL_0))
        taken = doc.timelines[FORM].components.pop(FIRST)
        with pytest.raises(IsADirectoryError):
            tla.write(tmp_path, doc)
        doc.timelines[FORM].components[FIRST] = taken
        written(doc, tmp_path)

    def test_with_no_length_it_leaves_the_states_read(self, tmp_path):
        doc = tla.loads(a_file(markers((FIRST, {"time": 150.0}))))
        kept = dict(doc.read_unmeasured)
        assert component_place(CADENCES, FIRST) in kept
        doc.timelines[CADENCES].components[FIRST].attrs["time"] = 1.5
        with pytest.raises(IsADirectoryError):
            tla.write(tmp_path, doc)
        assert doc.read_unmeasured == kept


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
            f"piece.tla: nothing was written: line {lines[0]}: Level can't be"
            f" below 1. Got '0'; line {lines[1]}: re\\ud83d is not a valid color."
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

    def test_writing_it_is_refused_with_a_kind_it_doesnt_know_first(
        self, without_music21, tmp_path
    ):
        # In id order: the first of the timeline can't say for the rest.
        doc = tla.loads(
            a_file(
                harmony_timeline((FIRST, {"kind": "FUTURE"}), (SECOND, harmony(1.0)))
            )
        )
        assert isinstance(
            doc.timelines[HARMONIES].components[FIRST].kind, tla.UnknownKind
        )
        path = tmp_path / "piece.tla"
        with pytest.raises(tla.BrokenRules, match="checking a harmony needs"):
            tla.write(path, doc)
        assert not path.exists()

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


class TestBeatWithoutATime:
    """The check's warning says it, as #285 asks; the rule it breaks adds none,
    and still refuses a new one."""

    @staticmethod
    def without_a_time(content):
        del content["timelines"][BEATS]["components"][BEAT_2]["time"]

    def test_it_has_one_warning_the_checks(self):
        data = a_file(self.without_a_time)
        assert tla.loads(data).warnings == [
            tla.ReadWarning(
                place=component_place(BEATS, BEAT_2),
                line=line_of(data, BEAT_2),
                message='a beat of the timeline "Beats" has no time',
            )
        ]

    def test_it_is_written_back_unchanged(self, tmp_path):
        data = a_file(self.without_a_time)
        path = tmp_path / "piece.tla"
        tla.write(path, tla.loads(data))
        assert path.read_bytes() == data

    def test_a_new_one_is_refused(self, tmp_path):
        data = a_file()
        doc = tla.loads(data)
        del doc.timelines[BEATS].components[BEAT_2].attrs["time"]
        path = tmp_path / "piece.tla"
        with pytest.raises(tla.BrokenRules) as refused:
            tla.write(path, doc)
        assert not path.exists()
        assert refused.value.problems == [
            tla.ReadWarning(
                place=component_place(BEATS, BEAT_2),
                line=line_of(data, BEAT_2),
                message="None is not a valid time.",
            )
        ]

    def test_a_change_to_one_is_refused(self, tmp_path):
        doc = tla.loads(a_file(self.without_a_time))
        doc.timelines[BEATS].components[BEAT_2].metadata["note"] = "seen"
        with pytest.raises(tla.BrokenRules):
            tla.write(tmp_path / "piece.tla", doc)

    def test_another_beats_time_is_still_warned_about_by_the_rules(self):
        def change(content):
            self.without_a_time(content)
            content["timelines"][BEATS]["components"][BEAT_1]["time"] = -1.0

        assert [w.message for w in tla.loads(a_file(change)).warnings] == [
            'a beat of the timeline "Beats" has no time',
            "Time can't be negative. Got '-00:01.0'",
        ]


class TestFingerprint:
    def test_a_write_expecting_a_fingerprint_keeps_the_files_problems(self, tmp_path):
        data = a_file(LEVEL_0)
        path = tmp_path / "piece.tla"
        path.write_bytes(data)
        tla.write(path, tla.read(path), expect=tla.fingerprint(path))
        assert path.read_bytes() == data

    @pytest.mark.parametrize(
        "data",
        [
            a_file(LEVEL_0),
            json.dumps(
                {
                    "file_path": "",
                    "media_path": "",
                    "media_metadata": {"media length": 60.0},
                    "timelines": {},
                    "app_name": "TiLiA",
                    "version": "0.6.0",
                }
            ).encode(),
        ],
        ids=["current", "old"],
    )
    def test_it_doesnt_check_the_rules(self, data, monkeypatch, tmp_path):
        def not_called(*args, **kwargs):
            raise AssertionError("the rules were checked")

        monkeypatch.setattr(rules, "check_timeline", not_called)
        monkeypatch.setattr(rules, "media_length", not_called)
        path = tmp_path / "piece.tla"
        path.write_bytes(data)
        assert len(tla.fingerprint(path)) == 64

    def test_it_is_the_fingerprint_of_what_reading_gives(self, tmp_path):
        data = a_file(LEVEL_0)
        path = tmp_path / "piece.tla"
        path.write_bytes(data)
        assert tla.fingerprint(path) == tla.fingerprint_of(tla.read(path))

    def test_it_is_refused_as_reading_refuses(self, tmp_path):
        path = tmp_path / "piece.tla"
        path.write_bytes(b"{}")
        with pytest.raises(tla.UnreadableFile):
            tla.fingerprint(path)


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
