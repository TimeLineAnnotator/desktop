"""What the reader keeps although it breaks a rule, with a warning, and what it
keeps without one: keys it doesn't know, at every level."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from tilia_core import rules, tla
from tilia_core.tla import reader, writer
from tilia_core.tla.ids import migrated_id

BROKEN = Path(__file__).parent / "broken"


def _load_make_broken():
    spec = importlib.util.spec_from_file_location(
        "make_broken", BROKEN / "make_broken.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


make_broken = _load_make_broken()
IDS = make_broken.IDS
FORM = IDS["form"]


def file_with(change):
    content = copy.deepcopy(make_broken.base())
    change(content)
    return make_broken.text_of(content).encode("utf-8")


def with_vocabulary(value, timeline="form"):
    def change(content):
        content["timelines"][IDS[timeline]]["metadata"] = {"vocabulary": value}

    return file_with(change)


# Vocabulary references (#31)


def test_an_invalid_vocabulary_reads_with_a_warning_naming_its_timeline():
    data = with_vocabulary("LCMA/Form@0.3")
    doc = tla.loads(data)
    assert doc.warnings == [
        tla.ReadWarning(
            place=f"/timelines/{FORM}/metadata/vocabulary",
            line=41,
            message='the vocabulary "LCMA/Form@0.3" of the timeline "Form"'
            " isn't a valid reference",
            timeline_id=FORM,
        )
    ]
    assert doc.timelines[FORM].metadata["vocabulary"] == "LCMA/Form@0.3"


def test_an_invalid_vocabulary_is_written_back_unchanged():
    data = with_vocabulary("LCMA/Form@0.3")
    doc = tla.loads(data)
    assert writer.checked_bytes(doc) == tla.canonical_bytes(doc) == data


def test_an_invalid_vocabulary_set_in_memory_is_written():
    # The writer refuses only what the reader refuses (FR-034).
    doc = tla.loads(make_broken.text_of(make_broken.base()).encode())
    doc.timelines[FORM].metadata["vocabulary"] = "LCMA/Form@0.3"
    assert tla.loads(writer.checked_bytes(doc)).warnings[0].place == (
        f"/timelines/{FORM}/metadata/vocabulary"
    )


@pytest.mark.parametrize(
    "value",
    ["lcma-form@0.3.0", "cadences", "form-2@10.20.30", "a", "0-9@0.0.0"],
)
def test_a_valid_vocabulary_reads_without_a_warning(value):
    assert tla.loads(with_vocabulary(value)).warnings == []


@pytest.mark.parametrize(
    "value",
    [
        "LCMA/Form@0.3",
        "lcma/form@0.3.0",  # "/" is kept free for a namespace
        "lcma-form@0.3",  # an incomplete version
        "lcma-form@0.3.0.1",
        "lcma-form@^0.3.0",  # a range, not an exact version
        "lcma-form@v0.3.0",
        "lcma-form@01.0.0",  # a number with a leading zero
        "lcma-form@",
        "@0.3.0",
        "Cadences",
        "café@1.0.0",  # a letter outside ASCII
        "lcma form",
        "lcma_form",
        "cadences\n",
        "",
        ["lcma-form@0.3.0"],
    ],
)
def test_an_invalid_vocabulary_reads_with_a_warning(value):
    doc = tla.loads(with_vocabulary(value))
    (warning,) = doc.warnings
    assert warning.place == f"/timelines/{FORM}/metadata/vocabulary"
    assert doc.timelines[FORM].metadata["vocabulary"] == value


def test_each_timeline_with_an_invalid_vocabulary_has_its_warning():
    def change(content):
        for name in ("form", "texture"):
            content["timelines"][IDS[name]]["metadata"] = {"vocabulary": "X"}

    doc = tla.loads(file_with(change))
    assert [(w.place, w.message) for w in doc.warnings] == [
        (
            f"/timelines/{IDS['form']}/metadata/vocabulary",
            'the vocabulary "X" of the timeline "Form" isn\'t a valid reference',
        ),
        (
            f"/timelines/{IDS['texture']}/metadata/vocabulary",
            'the vocabulary "X" of the timeline "Texture" isn\'t a valid reference',
        ),
    ]


def test_a_timeline_without_a_name_is_named_by_its_place():
    def change(content):
        form = content["timelines"][FORM]
        del form["name"]
        form["metadata"] = {"vocabulary": "X"}

    (warning,) = tla.loads(file_with(change)).warnings
    assert warning.message == (
        'the vocabulary "X" of a timeline without a name isn\'t a valid reference'
    )


def test_vocabulary_is_checked_only_on_timelines():
    # Elsewhere it is a field like any other.
    def change(content):
        content["metadata"]["vocabulary"] = "X"
        section = content["timelines"][FORM]["components"][IDS["section"]]
        section["metadata"] = {"vocabulary": "X"}

    assert tla.loads(file_with(change)).warnings == []


def test_a_warning_reads_as_its_line_and_message():
    (warning,) = tla.loads(with_vocabulary("X")).warnings
    assert str(warning) == (
        'line 41: the vocabulary "X" of the timeline "Form" isn\'t a valid reference'
    )
    assert str(tla.ReadWarning("/a", None, "a message")) == "a message"


def test_warnings_are_not_written():
    doc = tla.loads(with_vocabulary("X"))
    assert b"isn't a valid reference" not in tla.canonical_bytes(doc)


def test_a_file_without_problems_has_no_warnings():
    assert tla.loads(file_with(lambda content: None)).warnings == []


# A quality TiLiA offers


def test_a_v64_in_root_position_reads_with_no_warning():
    pytest.importorskip("music21", reason="needs the harmony extra")
    v64 = make_broken.make_id(100)

    def change(content):
        content["media"]["length"] = 60.0
        content["timelines"][IDS["nothing"]] = {
            "kind": "Harmony",
            "name": "Harmony",
            "ordinal": 6,
            "components": {
                v64: {
                    "kind": "HARMONY",
                    "time": 1.0,
                    "step": 4,
                    "quality": "cadential-six-four",
                    "inversion": 0,
                }
            },
        }

    doc = tla.loads(file_with(change))

    assert doc.warnings == []
    # The reader doesn't call the rules yet. This is the check it is to make.
    checked = rules.check_timeline(
        doc.media_length, doc.timelines[IDS["nothing"]].components.values()
    )
    assert checked[v64].outcome == rules.OK


# A component of a kind its timeline doesn't hold

KEPT = IDS["nothing"]


def with_component(component, timeline):
    def change(content):
        content["timelines"][IDS[timeline]]["components"][KEPT] = component

    return file_with(change)


def test_a_component_of_a_kind_its_timeline_doesnt_hold_reads_with_a_warning():
    # It isn't read as a range: the row it names isn't looked for.
    data = with_component(
        {"kind": "RANGE", "end": 2.0, "row_id": "nope", "start": 1.0}, "cadences"
    )
    assert tla.loads(data).warnings == [
        tla.ReadWarning(
            place=f"/timelines/{IDS['cadences']}/components/{KEPT}",
            line=65,
            message='the timeline "Cadences" holds a component of kind "RANGE", which'
            ' a timeline of kind "Marker" doesn\'t have: it is kept as it is',
            timeline_id=IDS["cadences"],
            component_id=KEPT,
        )
    ]


@pytest.mark.parametrize(
    "timeline, component",
    [
        ("texture", {"kind": "MARKER", "time": 1}),
        ("cadences", {"kind": "RANGE", "end": 2.0, "row_id": "nope", "start": 1.0}),
        # Its level stays 1.0, which a hierarchy's would not.
        ("cadences", {"kind": "HIERARCHY", "end": 2.0, "level": 1.0, "start": 0.0}),
        ("form", {"kind": "MARKER", "metadata": {}, "time": 1.0}),
        ("beats", {"kind": "MODE", "time": 1.0}),
        ("score_timeline", {"kind": "BEAT", "time": 1.0}),
    ],
)
def test_a_component_of_a_kind_its_timeline_doesnt_hold_is_kept_as_it_is(
    timeline, component
):
    # As a component of a kind the core doesn't know: its keys as they are,
    # none filled in, and written back the same.
    data = with_component(component, timeline)
    doc = tla.loads(data)
    kept = doc.timelines[IDS[timeline]].components[KEPT]
    assert kept.kind == tla.UnknownKind(component["kind"])
    assert kept.attrs == {}
    assert {"kind": kept.kind.spelling, "metadata": kept.metadata, **kept.extra} == {
        "metadata": {},
        **component,
    }
    (warning,) = doc.warnings
    assert warning.place == f"/timelines/{IDS[timeline]}/components/{KEPT}"
    assert writer.checked_bytes(doc) == data


@pytest.mark.parametrize("kind", ["Slider", "AudioWave"])
def test_a_timeline_that_holds_no_components_keeps_any_with_a_warning(kind):
    # A slider has none, and an AudioWave timeline's aren't stored.
    marker = make_broken.make_id(100)

    def change(content):
        content["timelines"][KEPT] = {
            "kind": kind,
            "name": kind,
            "ordinal": 6,
            "height": 40,
            "components": {marker: {"kind": "MARKER", "time": 1.0}},
        }

    data = file_with(change)
    doc = tla.loads(data)
    assert doc.timelines[KEPT].components[marker].kind == tla.UnknownKind("MARKER")
    (warning,) = doc.warnings
    assert warning.place == f"/timelines/{KEPT}/components/{marker}"
    assert writer.checked_bytes(doc) == data


# Keys the core doesn't know


def _pairs(pairs):
    return pairs


def keys_in_order(data):
    """Every object's keys in the order the file has them, by place."""
    found = {}

    def walk(value, place):
        if isinstance(value, list) and value and isinstance(value[0], tuple):
            found[place] = [key for key, _ in value]
            for key, item in value:
                walk(item, f"{place}/{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{place}/{index}")

    walk(json.loads(data, object_pairs_hook=_pairs), "")
    return found


UNKNOWN = {"zz": 1, "Zz": 2, "_x": [3], "ä": {"b": 1, "a": 2}, "a": None}
# In code-point order: capitals, then "_", then lower case, then "ä".
UNKNOWN_ORDER = ["Zz", "_x", "a", "zz", "ä"]


def _first(entries):
    return next(iter(entries.values()))


def _objects(content):
    """An object of each kind the reader knows, by the place the test names it.
    A score's source isn't among them: its unknown keys hold text (the
    schema's `additionalProperties`), as the golden unknown.tla's does."""
    beats = content["timelines"][IDS["beats"]]
    beat = beats["components"][IDS["beat_1"]]
    texture = content["timelines"][IDS["texture"]]
    score = content["scores"][0]
    return {
        "": content,
        "/media": content["media"],
        f"/timelines/{IDS['beats']}": beats,
        f"/timelines/{IDS['beats']}/components/{IDS['beat_1']}": beat,
        f"/timelines/{IDS['beats']}/components/{IDS['beat_1']}/measure": beat[
            "measure"
        ],
        f"/timelines/{IDS['beats']}/components/{IDS['beat_1']}/beat_unit": beat[
            "beat_unit"
        ],
        f"/timelines/{IDS['texture']}/rows/0": texture["rows"][0],
        "/scores/0": score,
    }


def test_unknown_keys_at_every_level_are_written_after_the_known_ones_in_code_point_order():
    expected = keys_in_order(make_broken.text_of(make_broken.base()))

    def change(content):
        # Given first, in another order: the writer puts them last, sorted.
        for value in _objects(content).values():
            known = dict(value)
            value.clear()
            value.update(dict(reversed(UNKNOWN.items())))
            value.update(known)

    doc = tla.loads(file_with(change))
    assert doc.warnings == []
    written = keys_in_order(tla.canonical_bytes(doc))
    for place in _objects(make_broken.base()):
        assert written[place] == expected.get(place, []) + UNKNOWN_ORDER, place
    again = tla.loads(tla.canonical_bytes(doc))
    assert tla.canonical_bytes(again) == tla.canonical_bytes(doc)
    assert again.extra["ä"] == {"b": 1, "a": 2}  # their own content as it is
    assert list(again.extra["ä"]) == ["b", "a"]


# Beat timelines


BEATS = IDS["beats"]
BEAT_1 = f"/timelines/{BEATS}/components/{IDS['beat_1']}"
BEAT_2 = f"/timelines/{BEATS}/components/{IDS['beat_2']}"


def beat(content, name):
    return content["timelines"][BEATS]["components"][IDS[name]]


def line_of(data, text):
    """The line of the first line of `data` that is `text`, stripped."""
    lines = [line.strip() for line in data.decode().split("\n")]
    return lines.index(text) + 1


def read_back_unchanged(data):
    doc = tla.loads(data)
    assert writer.checked_bytes(doc) == tla.canonical_bytes(doc) == data
    return doc


@pytest.mark.parametrize("units", ["x", "0", "1/0", "2+", "", "1/256", "-1"])
def test_units_tilia_cant_read_are_kept_with_a_warning(units):
    data = file_with(lambda c: beat(c, "beat_1")["beat_unit"].update(units=units))
    doc = read_back_unchanged(data)
    (warning,) = doc.warnings
    assert warning.place == f"{BEAT_1}/beat_unit/units"
    assert warning.line == line_of(data, f'"units": {json.dumps(units)}')
    assert warning.message == (
        f'a beat unit in the timeline "Beats" has units TiLiA can\'t read:'
        f" {json.dumps(units)}"
    )
    attrs = doc.timelines[BEATS].components[IDS["beat_1"]].attrs
    assert attrs["beat_unit"]["units"] == units


@pytest.mark.parametrize("denominator", [0, -4, 129])
def test_a_denominator_tilia_cant_read_is_kept_with_a_warning(denominator):
    def change(content):
        beat(content, "beat_1")["beat_unit"]["denominator"] = denominator

    doc = read_back_unchanged(file_with(change))
    (warning,) = doc.warnings
    assert warning.place == f"{BEAT_1}/beat_unit/denominator"
    assert warning.message == (
        'a beat unit in the timeline "Beats" has a denominator TiLiA can\'t'
        f" read: {denominator}"
    )


@pytest.mark.parametrize("units", ["1", "3", "1/2", "2+3", "1/3+1/3+1/3"])
def test_units_tilia_reads_have_no_warning(units):
    data = file_with(lambda c: beat(c, "beat_1")["beat_unit"].update(units=units))
    assert tla.loads(data).warnings == []


def test_two_beat_units_in_one_measure_are_kept_with_a_warning():
    def change(content):
        beat(content, "beat_2")["beat_unit"] = {"denominator": 8, "units": "3"}

    data = file_with(change)
    doc = read_back_unchanged(data)
    (warning,) = doc.warnings
    assert warning.place == f"{BEAT_2}/beat_unit"
    assert warning.message == "measure 1 has two beat units (TiLiA shows it red)"
    (row,) = doc.timelines[BEATS].measures.rows
    assert len(row.beat_units) == 2
    assert row.beat_unit == tla.BeatUnit(denominator=4, units="1")


def test_three_beat_units_in_one_measure_are_counted_in_the_warning():
    def change(content):
        second = beat(content, "beat_2")
        second["beat_unit"] = {"denominator": 8, "units": "3"}
        third = {
            **second,
            "time": second["time"] + 0.5,
            "beat_unit": {"denominator": 8, "units": "2"},
        }
        content["timelines"][BEATS]["components"][tla.new_id()] = third

    (warning,) = tla.loads(file_with(change)).warnings
    assert warning.place == f"{BEAT_2}/beat_unit"
    assert warning.message == "measure 1 has 3 beat units (TiLiA shows it red)"


def test_two_beat_units_in_a_measure_with_a_label_name_it_by_its_label():
    def change(content):
        beat(content, "beat_1")["measure"] = {"number": 14, "label": "14a"}
        beat(content, "beat_2")["beat_unit"] = {"denominator": 8, "units": "3"}

    (warning,) = tla.loads(file_with(change)).warnings
    assert warning.message == "measure 14a has two beat units (TiLiA shows it red)"


def test_two_beat_units_in_two_measures_have_no_warning():
    def change(content):
        beat(content, "beat_2")["measure"] = {}
        beat(content, "beat_2")["beat_unit"] = {"denominator": 8, "units": "3"}

    assert tla.loads(file_with(change)).warnings == []


def test_a_beat_unit_tilia_cant_read_doesnt_count_as_a_second_one():
    def change(content):
        beat(content, "beat_2")["beat_unit"] = {"denominator": 8, "units": "x"}

    doc = tla.loads(file_with(change))
    assert [w.place for w in doc.warnings] == [f"{BEAT_2}/beat_unit/units"]


def test_a_beat_without_a_time_is_kept_with_a_warning():
    data = file_with(lambda c: beat(c, "beat_2").pop("time"))
    doc = read_back_unchanged(data)
    assert doc.warnings == [
        tla.ReadWarning(
            place=BEAT_2,
            line=line_of(data, f'"{IDS["beat_2"]}": {{'),
            message='a beat of the timeline "Beats" has no time',
            timeline_id=BEATS,
            component_id=IDS["beat_2"],
        )
    ]


def test_a_closing_tap_with_a_measure_mark_is_kept_with_a_warning():
    # The mark stays in the file, and starts no measure
    # (TimeLineAnnotator/project-management#375).
    def change(content):
        beat(content, "beat_2").update(measure={"number": 7}, closing=True)

    data = file_with(change)
    doc = read_back_unchanged(data)
    assert doc.warnings == [
        tla.ReadWarning(
            place=BEAT_2,
            line=line_of(data, f'"{IDS["beat_2"]}": {{'),
            message='a closing tap in the timeline "Beats" has a measure mark,'
            " which starts no measure",
            timeline_id=BEATS,
            component_id=IDS["beat_2"],
        )
    ]
    (row,) = doc.timelines[BEATS].measures.rows
    assert row.beats == [IDS["beat_1"]]


@pytest.mark.parametrize(
    "following",
    [
        [make_broken.make_id(102)],  # names nothing
        [make_broken.make_id(101)],  # a beat without a mark
        [IDS["beat_1"]],  # a downbeat
    ],
    ids=["nothing", "a beat without a mark", "a downbeat"],
)
def test_a_closing_taps_next_is_kept_with_its_marks_warning(following):
    # The mark starts no measure, so its next isn't checked as a measure's:
    # it is kept, written back unchanged
    # (TimeLineAnnotator/project-management#375).
    def change(content):
        components = content["timelines"][BEATS]["components"]
        components[make_broken.make_id(101)] = {"kind": "BEAT", "time": 0.5}
        beat(content, "beat_2").update(measure={"next": following}, closing=True)

    data = file_with(change)
    doc = read_back_unchanged(data)
    assert [(w.place, w.message) for w in doc.warnings] == [
        (
            BEAT_2,
            'a closing tap in the timeline "Beats" has a measure mark, which'
            " starts no measure",
        )
    ]
    (row,) = doc.timelines[BEATS].measures.rows
    assert row.beats == [IDS["beat_1"], make_broken.make_id(101)]


@pytest.mark.parametrize(
    "closing, measure", [(True, None), (False, {}), (None, {})], ids=str
)
def test_a_closing_tap_without_a_mark_or_a_downbeat_has_no_warning(closing, measure):
    def change(content):
        if closing is not None:
            beat(content, "beat_2")["closing"] = closing
        if measure is not None:
            beat(content, "beat_2")["measure"] = measure

    assert tla.loads(file_with(change)).warnings == []


def with_role(content, name, role):
    """The timeline's role, in its place: before its components."""
    timeline = content["timelines"][IDS[name]]
    components = timeline.pop("components")
    timeline["metadata"] = {**timeline.get("metadata", {}), "role": role}
    timeline["components"] = components


def second_beat_timeline(content, ordinal=6, role="time_map"):
    content["timelines"][IDS["nothing"]] = {
        "kind": "Beat",
        "name": "Bars",
        "ordinal": ordinal,
        "height": 35,
        "metadata": {"role": role},
        "components": {
            make_broken.make_id(100): {"kind": "BEAT", "time": 0.0, "measure": {}}
        },
    }


def test_two_beat_timelines_claiming_time_map_warn_and_the_first_by_ordinal_wins():
    def change(content):
        with_role(content, "beats", "time_map")
        second_beat_timeline(content)

    data = file_with(change)
    doc = read_back_unchanged(data)
    (warning,) = doc.warnings
    assert warning.place == f"/timelines/{IDS['nothing']}/metadata/role"
    assert warning.message == (
        'the timeline "Bars" claims the role time_map, as the timeline "Beats"'
        " does, which comes first by ordinal and is the default"
    )


def test_the_first_by_ordinal_wins_whatever_the_files_order():
    # "Bars" comes last in the file, first by ordinal.
    def change(content):
        with_role(content, "beats", ["time_map", "analysis"])
        second_beat_timeline(content, ordinal=0)

    (warning,) = tla.loads(file_with(change)).warnings
    assert warning.place == f"/timelines/{BEATS}/metadata/role"
    assert 'as the timeline "Bars" does' in warning.message


def test_of_two_claimants_with_one_ordinal_the_default_is_the_time_maps():
    # "Bars" comes first in the file, "Beats" first by id: the time map takes
    # the timelines in the document's order, which is id order, and the
    # warning names the same default.
    from tilia_core.timemap import find_time_map

    def change(content):
        with_role(content, "beats", "time_map")
        second_beat_timeline(content, ordinal=1)
        timelines = content["timelines"]
        bars = timelines.pop(IDS["nothing"])
        content["timelines"] = {IDS["nothing"]: bars, **timelines}

    doc = tla.loads(file_with(change))
    (warning,) = doc.warnings
    assert warning.place == f"/timelines/{IDS['nothing']}/metadata/role"
    assert 'as the timeline "Beats" does' in warning.message
    assert find_time_map(doc).timeline_id == BEATS


def test_one_beat_timeline_claiming_time_map_has_no_warning():
    def change(content):
        with_role(content, "beats", "time_map")
        with_role(content, "form", "time_map")  # not a beat timeline: no table
        second_beat_timeline(content, role="analysis")

    assert tla.loads(file_with(change)).warnings == []


@pytest.mark.parametrize(
    "role, claims",
    [
        ("time_map", True),
        (["time_map"], True),
        (["analysis", "time_map"], True),
        ("analysis", False),
        (["analysis"], False),
        ("Time_Map", False),
        ("", False),
        ([], False),
    ],
    ids=str,
)
def test_the_check_and_the_time_map_agree_on_the_roles_that_claim_time_map(
    role, claims
):
    # One rule, which both read (TimeLineAnnotator/project-management#376).
    from tilia_core.timemap import find_time_map

    def change(content):
        with_role(content, "beats", "time_map")
        second_beat_timeline(content, role=role)

    doc = tla.loads(file_with(change))
    bars = IDS["nothing"]
    warned = f"/timelines/{bars}/metadata/role" in [w.place for w in doc.warnings]
    several = (
        f"timelines {BEATS} and {bars} claim the role time_map;"
        f" {BEATS}, the first by ordinal, is used"
    )
    assert warned is claims
    assert (several in find_time_map(doc).warnings) is claims


# The document's ids of what a warning concerns
# (TimeLineAnnotator/project-management#415)


OLD = Path(__file__).parent / "old"
SEVEN = OLD / "0.7.0.tla"


def concerns(warning):
    return warning.timeline_id, warning.component_id


def old_ids(place):
    """A place in an old file's old timeline and component ids."""
    steps = place.split("/")
    return steps[2], (steps[4] if len(steps) > 4 else None)


def test_a_warning_says_no_ids_unless_given_them():
    warning = tla.ReadWarning(place="/x", line=None, message="m")
    assert concerns(warning) == (None, None)


def test_a_warning_reads_as_it_did():
    warning = tla.ReadWarning(
        place="/x", line=3, message="m", timeline_id="a", component_id="b"
    )
    assert str(warning) == "line 3: m"


def test_a_vocabulary_warning_names_its_timeline_and_no_component():
    (warning,) = tla.loads(with_vocabulary("LCMA/Form@0.3")).warnings
    assert concerns(warning) == (FORM, None)


def test_a_broken_rules_warning_names_its_component():
    def change(content):
        content["timelines"][FORM]["components"][IDS["section"]]["level"] = 0

    (warning,) = tla.loads(file_with(change)).warnings
    assert concerns(warning) == (FORM, IDS["section"])
    assert warning.place == f"/timelines/{FORM}/components/{IDS['section']}"


def test_a_warning_about_a_key_of_a_component_names_that_component():
    # A place below the component's: a beat unit TiLiA can't read.
    beats = IDS["beats"]
    beat = IDS["beat_1"]

    def change(content):
        content["timelines"][beats]["components"][beat]["beat_unit"] = {
            "denominator": 4,
            "units": "not units",
        }

    doc = tla.loads(file_with(change))
    (warning,) = [w for w in doc.warnings if w.place.endswith("/beat_unit/units")]
    assert concerns(warning) == (beats, beat)


def test_a_component_of_a_kind_its_timeline_doesnt_hold_is_named():
    def change(content):
        content["timelines"][FORM]["components"][IDS["nothing"]] = {
            "kind": "MARKER",
            "time": 1.0,
        }

    doc = tla.loads(file_with(change))
    (warning,) = [w for w in doc.warnings if "kept as it is" in w.message]
    assert concerns(warning) == (FORM, IDS["nothing"])
    assert warning.component_id in doc.timelines[FORM].components


def test_a_problem_with_a_row_names_its_timeline_and_no_component():
    def change(content):
        content["timelines"][IDS["texture"]]["rows"][0]["color"] = "not a color"

    doc = tla.loads(file_with(change))
    (warning,) = [w for w in doc.warnings if "/rows/" in w.place]
    assert concerns(warning) == (IDS["texture"], None)


def test_a_problem_with_the_media_length_names_nothing():
    def change(content):
        content["media"]["length"] = -1.5

    doc = tla.loads(file_with(change))
    (warning,) = [w for w in doc.warnings if w.place == "/media/length"]
    assert concerns(warning) == (None, None)


def test_a_rule_a_write_refuses_names_what_it_is_about(tmp_path):
    doc = tla.loads(make_broken.text_of(make_broken.base()).encode())
    doc.timelines = {
        key: timeline
        for key, timeline in doc.timelines.items()
        if timeline.kind != "harmony"
    }
    doc.timelines[FORM].components[IDS["section"]].attrs["level"] = 0
    with pytest.raises(tla.BrokenRules) as caught:
        tla.write(tmp_path / "piece.tla", doc)
    (problem,) = caught.value.problems
    assert concerns(problem) == (FORM, IDS["section"])


def test_a_migration_warning_names_the_migrated_timeline_and_component():
    # What TiLiA shows: which hierarchy lost its `formal_type`, by its timeline
    # and time, though the old ids are gone from the document.
    data = SEVEN.read_bytes()
    old = json.loads(data)
    doc = tla.loads(data)
    formal = [
        w for w in doc.warnings if w.place.endswith(("formal_type", "formal_function"))
    ]
    assert len(formal) == 2
    for warning in formal:
        old_timeline, old_component = old_ids(warning.place)
        timeline = doc.timelines[warning.timeline_id]
        component = timeline.components[warning.component_id]
        assert component.kind == "hierarchy"
        was = old["timelines"][old_timeline]["components"][old_component]
        assert timeline.name == old["timelines"][old_timeline]["name"]
        assert component.attrs["start"] == was["start"]
        assert component.attrs["end"] == was["end"]
        assert component.attrs["level"] == was["level"]
        # Still at its place in the old file, with the old ids.
        assert warning.place.startswith(
            f"/timelines/{old_timeline}/components/{old_component}/"
        )


def test_the_ids_of_a_migration_warning_are_those_derived_for_its_old_ids():
    data = SEVEN.read_bytes()
    doc = tla.loads(data)
    positions = {key: index for index, key in enumerate(json.loads(data)["timelines"])}
    (warning, *_) = [w for w in doc.warnings if w.place.endswith("formal_type")]
    old_timeline, old_component = old_ids(warning.place)
    assert warning.timeline_id == migrated_id(
        doc.document_id, "timeline", old_timeline, position=positions[old_timeline]
    )
    timeline = json.loads(data)["timelines"][old_timeline]["components"]
    index = list(timeline).index(old_component)
    assert warning.component_id == migrated_id(
        doc.document_id, "component", old_timeline, old_component, position=index
    )


def test_the_migrations_own_warnings_have_the_ids_before_the_reader_adds_a_line():
    _, migrated = reader.read_with_migration(SEVEN)
    (first, *_) = migrated.warnings
    assert first.line is None
    assert first.timeline_id is not None
    assert first.component_id is not None


def test_amplitude_bars_dropped_name_their_timeline_and_no_component():
    doc = tla.loads(SEVEN.read_bytes())
    (warning,) = [w for w in doc.warnings if "amplitude bar" in w.message]
    assert doc.timelines[warning.timeline_id].kind == "audiowave"
    assert warning.component_id is None


def old_beats(times, **timeline):
    """An old file with a beat timeline, whose beats are at `times`."""
    return {
        "app_name": "TiLiA",
        "version": "0.7.0",
        "media_path": "",
        "media_metadata": {"media length": 10},
        "timelines": {
            "9": {
                "kind": "Beat",
                "name": "Beats",
                "ordinal": 1,
                "height": 40,
                "is_visible": True,
                "beat_pattern": [4],
                "components": {
                    str(index + 10): {"kind": "BEAT", "time": time}
                    for index, time in enumerate(times)
                },
                **timeline,
            }
        },
    }


def read_old(content):
    return tla.loads(json.dumps(content).encode())


def test_a_beat_the_migration_dropped_names_its_timeline_and_no_component():
    doc = read_old(old_beats([0.0, 1.0, 50.0]))
    (warning,) = [w for w in doc.warnings if "outside the media" in w.message]
    assert warning.place == "/timelines/9/components/12"
    assert warning.timeline_id in doc.timelines
    assert doc.timelines[warning.timeline_id].name == "Beats"
    assert warning.component_id is None


def test_a_beat_unit_the_migration_dropped_names_its_timeline_and_no_component():
    content = old_beats([0.0, 1.0])
    content["timelines"]["9"]["components"]["20"] = {
        "kind": "BEAT_UNIT",
        "beat_id": "99",
        "denominator": 4,
        "units": "1",
    }
    doc = read_old(content)
    (warning,) = [w for w in doc.warnings if "beat unit" in w.message]
    assert warning.place == "/timelines/9/components/20"
    assert doc.timelines[warning.timeline_id].name == "Beats"
    assert warning.component_id is None


def test_a_beat_timeline_tilia_cant_open_names_its_timeline_and_no_component():
    doc = read_old(old_beats([0.0, 1.0], beats_in_measure="not a list"))
    (warning,) = [w for w in doc.warnings if "can't open" in w.message]
    assert warning.place == "/timelines/9/beats_in_measure"
    assert doc.timelines[warning.timeline_id].name == "Beats"
    assert warning.component_id is None


def test_the_rules_warning_in_an_old_file_names_the_migrated_component():
    data = SEVEN.read_bytes().replace(b'"level": 1,', b'"level": 0,', 1)
    doc = tla.loads(data)
    (warning,) = [w for w in doc.warnings if "Level can't be below 1" in w.message]
    # Named in the old file's terms, with the document's ids.
    assert warning.place.startswith("/timelines/1/components/")
    component = doc.timelines[warning.timeline_id].components[warning.component_id]
    assert component.attrs["level"] == 0


def test_the_checks_warning_in_an_old_file_names_the_migrated_component():
    data = SEVEN.read_bytes().replace(b'"kind": "MODE"', b'"kind": "MARKER"')
    doc = tla.loads(data)
    (warning,) = [w for w in doc.warnings if "kept as it is" in w.message]
    assert warning.place == "/timelines/22/components/23"
    timeline = doc.timelines[warning.timeline_id]
    assert timeline.kind == "harmony"
    component = timeline.components[warning.component_id]
    assert component.kind == tla.UnknownKind("MARKER")


def test_an_old_timeline_id_a_pointer_escapes_is_followed():
    content = old_beats([0.0, 1.0], beats_in_measure="not a list")
    content["timelines"]["a/b~c"] = content["timelines"].pop("9")
    doc = read_old(content)
    (warning,) = [w for w in doc.warnings if "can't open" in w.message]
    assert warning.place == "/timelines/a~1b~0c/beats_in_measure"
    assert doc.timelines[warning.timeline_id].name == "Beats"


def test_an_old_component_id_a_pointer_escapes_is_followed():
    content = old_beats([])
    content["timelines"]["9"] = {
        "kind": "Hierarchy",
        "name": "Form",
        "ordinal": 1,
        "height": 40,
        "is_visible": True,
        "components": {
            "a/b~c": {
                "kind": "HIERARCHY",
                "start": 0.0,
                "end": 1.0,
                "level": 1,
                "formal_type": "sonata form",
            }
        },
    }
    doc = read_old(content)
    (warning,) = doc.warnings
    assert warning.place == "/timelines/9/components/a~1b~0c/formal_type"
    timeline = doc.timelines[warning.timeline_id]
    assert timeline.components[warning.component_id].attrs["end"] == 1.0


@pytest.mark.parametrize("path", sorted(OLD.glob("*.tla")), ids=lambda path: path.name)
def test_every_id_a_warning_names_in_an_old_file_is_in_its_document(path):
    doc = tla.read(path)
    for warning in doc.warnings:
        if warning.timeline_id is not None:
            timeline = doc.timelines[warning.timeline_id]
            if warning.component_id is not None:
                assert warning.component_id in timeline.components
        else:
            assert warning.component_id is None
