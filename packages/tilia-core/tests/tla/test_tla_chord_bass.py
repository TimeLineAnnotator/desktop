"""A chord's real bass (TimeLineAnnotator/project-management#514): `bass_step` and
`bass_accidental`, in the terms of `step` and `accidental`, after `inversion`,
where the inversion doesn't already give that bass, as in C/Eb. Without them, as
in every older file, the bass is the inversion's, and no file gains a line."""

import json
from pathlib import Path

import jsonschema
import pytest

from tilia_core import rules, tla
from tilia_core.tla import layout

HERE = Path(__file__).parent
EVERY_FILE = sorted([*(HERE / "golden").glob("*.tla"), *(HERE / "old").glob("*.tla")])
# C/Eb: inversion 1 gives E.
C_OVER_E_FLAT = {
    "time": 1.0,
    "step": 0,
    "quality": "major",
    "inversion": 1,
    "bass_step": 2,
    "bass_accidental": -1,
}


def document(attrs, *, metadata=None):
    """A harmony timeline holding one chord, and its ids."""
    component = tla.Component(
        id=tla.new_id(), kind="harmony", attrs=dict(attrs), metadata=metadata or {}
    )
    timeline = tla.Timeline(
        id=tla.new_id(),
        kind="harmony",
        ordinal=1,
        components={component.id: component},
    )
    doc = tla.new_document()
    doc.media_length = 60.0
    doc.timelines[timeline.id] = timeline
    return doc, timeline.id, component.id


def component_in(data, timeline_id, component_id):
    return json.loads(data)["timelines"][timeline_id]["components"][component_id]


def test_a_chord_with_its_bass_has_it_after_inversion():
    doc, timeline, component = document(C_OVER_E_FLAT, metadata={"tags": ["slash"]})
    written = component_in(tla.canonical_bytes(doc), timeline, component)
    # Its step and quality are at their default, and left out. Before the metadata,
    # not after the known keys.
    assert list(written) == [
        "kind",
        "time",
        "inversion",
        "bass_step",
        "bass_accidental",
        "metadata",
    ]
    assert (written["bass_step"], written["bass_accidental"]) == (2, -1)


def test_they_come_between_inversion_and_applied_to():
    doc, timeline, component = document({**C_OVER_E_FLAT, "applied_to": 4})
    keys = list(component_in(tla.canonical_bytes(doc), timeline, component))
    at = keys.index("inversion")
    assert keys[at : at + 4] == [
        "inversion",
        "bass_step",
        "bass_accidental",
        "applied_to",
    ]


def test_a_natural_bass_keeps_its_accidental():
    # They are written together: C/D holds accidental 0, though 0 is `accidental`'s
    # default, and C/C# holds step 0.
    doc, timeline, component = document(
        {"time": 1.0, "bass_step": 0, "bass_accidental": 0}
    )
    written = component_in(tla.canonical_bytes(doc), timeline, component)
    assert (written["bass_step"], written["bass_accidental"]) == (0, 0)


def test_a_chord_with_its_bass_reads_it_as_attributes():
    doc, timeline, component = document(C_OVER_E_FLAT)
    read = tla.loads(tla.canonical_bytes(doc)).timelines[timeline]
    attrs = read.components[component].attrs
    assert (attrs["bass_step"], attrs["bass_accidental"]) == (2, -1)
    assert read.components[component].extra == {}


def test_a_second_write_changes_no_byte():
    doc, _, _ = document(C_OVER_E_FLAT)
    first = tla.canonical_bytes(doc)
    assert tla.canonical_bytes(tla.loads(first)) == first


def test_a_write_and_a_second_write_change_no_byte(tmp_path):
    pytest.importorskip("music21", reason="writing a harmony needs the harmony extra")
    doc, _, _ = document(C_OVER_E_FLAT)
    path = tmp_path / "piece.tla"
    tla.write(path, doc)
    first = path.read_bytes()
    read = tla.read(path)
    assert read.warnings == []
    tla.write(path, read)
    assert path.read_bytes() == first


@pytest.mark.parametrize(
    "attrs",
    [
        {"time": 1.0, "step": 0},
        {"time": 1.0, "step": 0, "bass_step": None, "bass_accidental": None},
    ],
    ids=["no keys", "None given for them"],
)
def test_a_chord_without_its_bass_leaves_them_out(attrs):
    doc, timeline, component = document(attrs)
    data = tla.canonical_bytes(doc)
    assert list(component_in(data, timeline, component)) == ["kind", "time"]


def test_a_null_for_either_is_a_missing_key():
    doc, timeline, component = document({"time": 1.0})
    without = tla.canonical_bytes(doc)
    content = json.loads(without)
    held = content["timelines"][timeline]["components"][component]
    held.update(bass_step=None, bass_accidental=None)
    read = tla.loads(json.dumps(content).encode())
    attrs = read.timelines[timeline].components[component].attrs
    assert "bass_step" not in attrs
    assert "bass_accidental" not in attrs
    assert tla.canonical_bytes(read) == without


@pytest.mark.parametrize("path", EVERY_FILE, ids=lambda path: path.name)
def test_no_old_or_golden_file_gains_a_line(path):
    assert b'"bass_' not in path.read_bytes()
    assert b'"bass_' not in tla.canonical_bytes(tla.read(path))


def test_neither_has_a_default_the_reader_fills_in():
    # So a chord without them reads without them, and either is written when set.
    shape = layout.COMPONENT_SHAPES["harmony"]
    assert not {"bass_step", "bass_accidental"} & shape.defaults.keys()
    assert not {"bass_step", "bass_accidental"} & shape.always


# The rules


@pytest.mark.parametrize("value", [*range(7)])
def test_bass_step_takes_steps_values(value):
    found = rules.check_timeline(
        60.0, [tla.Component(id="a", kind="harmony", attrs=_attrs(bass_step=value))]
    )
    assert found["a"].outcome.ok


@pytest.mark.parametrize("value", rules.HARMONY_ACCIDENTALS)
def test_bass_accidental_takes_accidentals_values(value):
    found = rules.check_timeline(
        60.0,
        [tla.Component(id="a", kind="harmony", attrs=_attrs(bass_accidental=value))],
    )
    assert found["a"].outcome.ok


def _attrs(**given):
    return {"time": 1.0, **given}


@pytest.mark.parametrize(
    "name, value, reason, code",
    [
        ("bass_step", 7, "7 is not a valid bass step.", "bad_bass_step"),
        ("bass_step", -1, "-1 is not a valid bass step.", "bad_bass_step"),
        ("bass_step", True, "True is not a valid bass step.", "bad_bass_step"),
        ("bass_step", "E", "E is not a valid bass step.", "bad_bass_step"),
        (
            "bass_accidental",
            3,
            "3 is not a valid bass accidental.",
            "bad_bass_accidental",
        ),
        (
            "bass_accidental",
            -3,
            "-3 is not a valid bass accidental.",
            "bad_bass_accidental",
        ),
    ],
)
def test_another_value_breaks_the_rule(name, value, reason, code):
    found = rules.check_timeline(
        60.0, [tla.Component(id="a", kind="harmony", attrs=_attrs(**{name: value}))]
    )
    outcome = found["a"].outcome
    assert (outcome.ok, outcome.reason, outcome.code) == (False, reason, code)
    assert reason == rules.not_valid(name, value)


def file_with(**attrs):
    doc, timeline, component = document({"time": 1.0, **attrs})
    return tla.canonical_bytes(doc), timeline, component


def test_the_reader_keeps_a_value_that_breaks_the_rule_with_a_warning():
    data, timeline, component = file_with(bass_step=7, bass_accidental=0)
    doc = tla.loads(data)
    (warning,) = [w for w in doc.warnings if "bass" in w.message]
    assert warning.message == "7 is not a valid bass step."
    assert warning.place == f"/timelines/{timeline}/components/{component}"
    assert doc.timelines[timeline].components[component].attrs["bass_step"] == 7
    assert tla.canonical_bytes(doc) == data


def test_the_writer_refuses_a_new_value_that_breaks_the_rule(tmp_path):
    doc, timeline, component = document(C_OVER_E_FLAT)
    doc.timelines[timeline].components[component].attrs["bass_accidental"] = 5
    with pytest.raises(tla.BrokenRules) as refused:
        tla.write(tmp_path / "piece.tla", doc)
    assert any(
        problem.message == "5 is not a valid bass accidental."
        for problem in refused.value.problems
    )


@pytest.mark.parametrize(
    "name, value, message",
    [
        ("bass_step", "E", '"bass_step" should be an integer or null, not text'),
        (
            "bass_accidental",
            "b",
            '"bass_accidental" should be an integer or null, not text',
        ),
    ],
)
def test_the_wrong_type_is_refused_by_the_core_and_the_schema(name, value, message):
    doc, timeline, component = document({"time": 1.0})
    content = json.loads(tla.canonical_bytes(doc))
    content["timelines"][timeline]["components"][component][name] = value
    assert not jsonschema.Draft202012Validator(tla.schema()).is_valid(content)
    with pytest.raises(tla.UnreadableFile) as caught:
        tla.loads(json.dumps(content).encode())
    assert caught.value.message == message


def test_an_integer_written_as_1_0_is_read_as_the_integer():
    data, timeline, component = file_with()
    content = json.loads(data)
    held = content["timelines"][timeline]["components"][component]
    held.update(bass_step=2.0, bass_accidental=-1.0)
    read = tla.loads(json.dumps(content).encode())
    attrs = read.timelines[timeline].components[component].attrs
    assert isinstance(attrs["bass_step"], int)
    assert (attrs["bass_step"], attrs["bass_accidental"]) == (2, -1)


# The schema


def test_the_schema_accepts_both_on_a_harmony():
    doc, _, _ = document(C_OVER_E_FLAT)
    jsonschema.validate(json.loads(tla.canonical_bytes(doc)), tla.schema())


def test_the_schema_names_them_on_a_harmony_and_no_other_kind():
    component = tla.schema()["$defs"]["component"]
    naming = []
    for branch in component["allOf"]:
        test = branch["if"]["properties"]["kind"]
        for spelling in test.get("enum", [test.get("const")]):
            names = branch["then"].get("properties", {})
            if "bass_step" in names or "bass_accidental" in names:
                naming.append(spelling)
    assert naming == ["HARMONY"]


# With one and not the other, which is open


@pytest.mark.parametrize(
    "attrs",
    [{"bass_step": 2}, {"bass_accidental": -1}],
    ids=["bass_step alone", "bass_accidental alone"],
)
def test_a_chord_with_one_of_the_two_is_read_and_written_as_it_is(attrs):
    # What the reader does until TimeLineAnnotator/project-management#522
    # is answered: it keeps the key, says nothing, and writes it back.
    data, timeline, component = file_with(**attrs)
    doc = tla.loads(data)
    assert [w for w in doc.warnings if "bass" in w.message] == []
    assert doc.read_problems == []
    held = doc.timelines[timeline].components[component].attrs
    assert {key: held[key] for key in attrs} == attrs
    assert tla.canonical_bytes(doc) == data
