"""What the reader keeps although it breaks a rule, with a warning, and what it
keeps without one: keys it doesn't know, at every level."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from tilia_core import tla
from tilia_core.tla import writer

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
