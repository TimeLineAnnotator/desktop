"""A time signature's `pairs` (TimeLineAnnotator/project-management#511): a key
of the format, after `denominator`, for a composite time signature such as
2/4 + 3/8, and left out when it has none, so that no file gains a line. Every
other attribute of a legacy score's kinds is still written whatever its value."""

import json
from pathlib import Path

import jsonschema
import pytest

from tilia_core import tla
from tilia_core.tla import layout

HERE = Path(__file__).parent
OLD = HERE / "old"
GOLDEN = HERE / "golden"
PAIRS = [["2", 4], ["3", 8]]
COMPOSITE = {
    "staff_index": 0,
    "time": 1.5,
    "numerator": None,
    "denominator": None,
    "pairs": PAIRS,
}
PLAIN = {"staff_index": 0, "time": 0.0, "numerator": "3", "denominator": 4}
# The old files that hold a time signature, and what TiLiA stored for one.
WITH_TIME_SIGNATURE = sorted(
    path for path in OLD.glob("*.tla") if b'"TIME_SIGNATURE"' in path.read_bytes()
)


def document(attrs, *, kind="time_signature", metadata=None, extra=None):
    """A score timeline holding one component, and its ids."""
    component = tla.Component(
        id=tla.new_id(),
        kind=kind,
        attrs=dict(attrs),
        metadata=metadata or {},
        extra=extra or {},
    )
    timeline = tla.Timeline(
        id=tla.new_id(),
        kind="score",
        ordinal=1,
        attrs={"height": 80},
        components={component.id: component},
    )
    doc = tla.new_document()
    doc.timelines[timeline.id] = timeline
    return doc, timeline.id, component.id


def component_in(data, timeline_id, component_id):
    return json.loads(data)["timelines"][timeline_id]["components"][component_id]


def test_a_time_signature_with_pairs_has_them_after_denominator(tmp_path):
    doc, timeline, component = document(COMPOSITE, metadata={"tags": ["composite"]})
    path = tmp_path / "piece.tla"
    tla.write(path, doc)
    written = component_in(path.read_bytes(), timeline, component)
    # Before the metadata, not after the known keys.
    assert list(written) == [
        "kind",
        "staff_index",
        "time",
        "numerator",
        "denominator",
        "pairs",
        "metadata",
    ]
    assert written["pairs"] == PAIRS
    # What a composite time signature holds in its place stays: a null.
    assert written["numerator"] is None
    assert written["denominator"] is None


def test_a_time_signature_with_pairs_reads_as_an_attribute(tmp_path):
    doc, timeline, component = document(COMPOSITE)
    path = tmp_path / "piece.tla"
    tla.write(path, doc)
    read = tla.read(path).timelines[timeline].components[component]
    assert read.attrs["pairs"] == PAIRS
    assert read.extra == {}


def test_a_second_write_of_a_time_signature_with_pairs_changes_no_byte(tmp_path):
    doc, _, _ = document(COMPOSITE)
    path = tmp_path / "piece.tla"
    tla.write(path, doc)
    first = path.read_bytes()
    assert tla.canonical_bytes(tla.read(path)) == first
    tla.write(path, tla.read(path))
    assert path.read_bytes() == first


@pytest.mark.parametrize(
    "attrs",
    [PLAIN, {**PLAIN, "pairs": None}],
    ids=["no key", "None given for the key"],
)
def test_a_time_signature_without_pairs_leaves_the_key_out(tmp_path, attrs):
    doc, timeline, component = document(attrs)
    path = tmp_path / "piece.tla"
    tla.write(path, doc)
    written = component_in(path.read_bytes(), timeline, component)
    assert list(written) == ["kind", "staff_index", "time", "numerator", "denominator"]
    assert b'"pairs"' not in path.read_bytes()


def test_a_null_for_pairs_is_a_missing_key():
    # TiLiA writes one on every time signature it saves since 0.7.2.
    doc, timeline, component = document(PLAIN)
    without = tla.canonical_bytes(doc)
    content = json.loads(without)
    content["timelines"][timeline]["components"][component]["pairs"] = None
    read = tla.loads(json.dumps(content).encode())
    read_component = read.timelines[timeline].components[component]
    assert "pairs" not in read_component.attrs
    assert read_component.extra == {}
    assert tla.canonical_bytes(read) == without


@pytest.mark.parametrize("path", sorted(GOLDEN.glob("*.tla")), ids=lambda p: p.name)
def test_the_golden_files_hold_no_pairs(path):
    assert b'"pairs"' not in path.read_bytes()
    assert tla.canonical_bytes(tla.read(path)) == path.read_bytes()


def test_old_files_with_time_signatures_are_tested():
    assert len(WITH_TIME_SIGNATURE) >= 3


@pytest.mark.parametrize("path", sorted(OLD.glob("*.tla")), ids=lambda p: p.name)
def test_an_old_file_without_pairs_gains_no_line(path):
    assert b'"pairs"' not in path.read_bytes()
    assert b'"pairs"' not in tla.canonical_bytes(tla.read(path))


def with_pairs_in_each_time_signature(path, pairs):
    content = json.loads(path.read_bytes())
    found = 0
    for timeline in content["timelines"].values():
        for component in timeline["components"].values():
            if component["kind"] == "TIME_SIGNATURE":
                component["pairs"] = pairs
                found += 1
    assert found
    return json.dumps(content).encode()


@pytest.mark.parametrize("path", WITH_TIME_SIGNATURE, ids=lambda p: p.name)
def test_an_old_files_null_for_pairs_gains_no_line_when_migrated(path):
    # As TiLiA 0.7.2 and later save a time signature without pairs.
    saved = tla.loads(with_pairs_in_each_time_signature(path, None))
    assert b'"pairs"' not in tla.canonical_bytes(saved)


def as_saved_by_tilia_0_7_2(path, **change):
    """The old file at `path` as TiLiA 0.7.2 and later save it with no edit: each
    time signature's numerator as text, and `"pairs": null`; then `change`d."""
    content = json.loads(path.read_bytes())
    found = 0
    for timeline in content["timelines"].values():
        for component in timeline["components"].values():
            if component["kind"] == "TIME_SIGNATURE":
                component["numerator"] = str(component["numerator"])
                component["pairs"] = None
                component.update(change)
                found += 1
    assert found
    return json.dumps(content).encode()


@pytest.mark.parametrize("path", WITH_TIME_SIGNATURE, ids=lambda p: p.name)
def test_an_old_file_saved_again_by_tilia_0_7_2_keeps_its_document_id(path):
    before = tla.loads(path.read_bytes())
    after = tla.loads(as_saved_by_tilia_0_7_2(path))
    assert after.document_id == before.document_id
    # So do its timelines and components, whose ids are derived from it.
    assert after.timelines.keys() == before.timelines.keys()
    for key, timeline in after.timelines.items():
        assert timeline.components.keys() == before.timelines[key].components.keys()


@pytest.mark.parametrize("path", WITH_TIME_SIGNATURE, ids=lambda p: p.name)
def test_the_file_keeps_the_numerator_as_tilia_0_7_2_saved_it(path):
    # Only the id's computation counts it as a number.
    data = tla.canonical_bytes(tla.loads(as_saved_by_tilia_0_7_2(path)))
    for timeline in json.loads(data)["timelines"].values():
        for component in timeline["components"].values():
            if component["kind"] == "TIME_SIGNATURE":
                assert isinstance(component["numerator"], str)
                assert "pairs" not in component


@pytest.mark.parametrize(
    "change",
    [
        {"numerator": "7"},
        {"numerator": "3+2"},
        # 0.7.0.tla's is 2: TiLiA writes it "2", and "02" is other text.
        {"numerator": "02"},
        {"pairs": [["2", 4], ["3", 8]]},
        {"denominator": 16},
    ],
    ids=[
        "another numerator",
        "a composite one",
        "with a leading 0",
        "pairs",
        "denominator",
    ],
)
def test_an_edit_still_changes_the_document_id(change):
    path = OLD / "0.7.0.tla"
    plain = tla.loads(as_saved_by_tilia_0_7_2(path))
    edited = tla.loads(as_saved_by_tilia_0_7_2(path, **change))
    assert edited.document_id != plain.document_id


def test_only_a_time_signature_of_a_score_timeline_is_seen_so():
    # Text elsewhere stays text: in a component of another kind, and in a time
    # signature kept in a timeline that doesn't hold one.
    from tilia_core.tla.ids import derived_document_id

    def with_one(timeline_kind, kind, key, value):
        component = {"kind": kind, "time": 1.0, key: value}
        timeline = {"kind": timeline_kind, "components": {"2": component}}
        return {"timelines": {"1": timeline}}

    def seen_alike(*shape):
        return derived_document_id(with_one(*shape, "3")) == derived_document_id(
            with_one(*shape, 3)
        )

    assert seen_alike("Score", "TIME_SIGNATURE", "numerator")
    assert not seen_alike("Score", "NOTE", "numerator")
    assert not seen_alike("Hierarchy", "TIME_SIGNATURE", "numerator")
    assert not seen_alike("Score", "TIME_SIGNATURE", "denominator")


@pytest.mark.parametrize("path", WITH_TIME_SIGNATURE, ids=lambda p: p.name)
def test_an_old_files_pairs_are_kept_in_their_place(path):
    doc = tla.loads(with_pairs_in_each_time_signature(path, PAIRS))
    data = tla.canonical_bytes(doc)
    found = 0
    for timeline in json.loads(data)["timelines"].values():
        for component in timeline["components"].values():
            if component["kind"] == "TIME_SIGNATURE":
                keys = list(component)
                assert keys[keys.index("denominator") + 1] == "pairs"
                assert component["pairs"] == PAIRS
                found += 1
    assert found
    assert tla.canonical_bytes(tla.loads(data)) == data


def as_written_when_pairs_was_unknown(data, timeline, component):
    """`data` with the time signature's keys as the core wrote them while it
    didn't know `pairs`: after the known keys, metadata included."""
    content = json.loads(data)
    held = content["timelines"][timeline]["components"]
    keys = held[component]
    keys["pairs"] = keys.pop("pairs")
    return (json.dumps(content, indent=2, ensure_ascii=False) + "\n").encode()


def test_a_file_written_while_pairs_was_unknown_reads_the_same(tmp_path):
    doc, timeline, component = document(COMPOSITE, metadata={"tags": ["composite"]})
    data = tla.canonical_bytes(doc)
    earlier = as_written_when_pairs_was_unknown(data, timeline, component)
    keys = list(component_in(earlier, timeline, component))
    assert keys[-2:] == ["metadata", "pairs"]
    assert earlier != data

    read = tla.loads(earlier)
    assert read == tla.loads(data)
    assert read.timelines[timeline].components[component].attrs["pairs"] == PAIRS

    # Written in the layout's order, and stable from there.
    path = tmp_path / "piece.tla"
    path.write_bytes(earlier)
    tla.write(path, tla.read(path))
    assert path.read_bytes() == data
    assert tla.canonical_bytes(tla.read(path)) == data


def test_a_file_written_while_pairs_was_unknown_keeps_its_fingerprint(tmp_path):
    # Its key order is one the layout fixes (FR-043).
    doc, timeline, component = document(COMPOSITE, metadata={"tags": ["composite"]})
    data = tla.canonical_bytes(doc)
    path = tmp_path / "piece.tla"
    path.write_bytes(as_written_when_pairs_was_unknown(data, timeline, component))
    assert tla.fingerprint(path) == tla.fingerprint_of(tla.loads(data))


def test_pairs_given_as_a_key_the_core_doesnt_know_are_written_in_their_place():
    # What a caller from before the key holds still lands where the layout says.
    doc, timeline, component = document(
        PLAIN, metadata={"tags": ["composite"]}, extra={"pairs": PAIRS}
    )
    keys = list(component_in(tla.canonical_bytes(doc), timeline, component))
    assert keys[keys.index("denominator") + 1] == "pairs"


def test_on_another_kind_pairs_is_a_key_the_core_doesnt_know():
    bar_line = {"time": 1.0}
    doc, timeline, component = document(
        bar_line,
        kind="bar_line",
        metadata={"tags": ["x"]},
        extra={"pairs": PAIRS},
    )
    data = tla.canonical_bytes(doc)
    assert list(component_in(data, timeline, component)) == [
        "kind",
        "time",
        "metadata",
        "pairs",
    ]
    read = tla.loads(data).timelines[timeline].components[component]
    assert read.extra == {"pairs": PAIRS}
    assert "pairs" not in read.attrs


@pytest.mark.parametrize(
    "kind", sorted(layout.LEGACY_SCORE_COMPONENTS - {"time_signature"})
)
def test_the_other_legacy_kinds_still_write_every_attribute(kind):
    shape = layout.COMPONENT_SHAPES[kind]
    assert shape.always - {"kind"} == frozenset(layout.COMPONENT_ATTRIBUTES[kind])
    assert not shape.defaults


def test_a_time_signatures_other_attributes_are_written_whatever_their_value():
    shape = layout.COMPONENT_SHAPES["time_signature"]
    assert shape.always - {"kind"} == {
        "staff_index",
        "time",
        "numerator",
        "denominator",
    }
    assert not shape.defaults


def test_the_schema_accepts_pairs_on_a_time_signature():
    doc, _, _ = document(COMPOSITE)
    jsonschema.validate(json.loads(tla.canonical_bytes(doc)), tla.schema())


def legacy_branches():
    component = tla.schema()["$defs"]["component"]
    for branch in component["allOf"]:
        test = branch["if"]["properties"]["kind"]
        for spelling in test.get("enum", [test.get("const")]):
            yield spelling, branch["then"]


def test_the_schema_names_pairs_on_a_time_signature_and_no_other_kind():
    naming = [
        spelling
        for spelling, then in legacy_branches()
        if "pairs" in then.get("properties", {})
    ]
    assert naming == ["TIME_SIGNATURE"]


def with_pairs(doc, pairs):
    """The content of `doc`, whose one component is a time signature, holding `pairs`."""
    content = json.loads(tla.canonical_bytes(doc))
    for timeline in content["timelines"].values():
        for component in timeline["components"].values():
            component["pairs"] = pairs
    return content


@pytest.mark.parametrize(
    "pairs, message, place",
    [
        ("2/4 + 3/8", '"pairs" should be a list or null, not text', "pairs"),
        ({"2": 4}, '"pairs" should be a list or null, not an object', "pairs"),
        (["2", 4], 'an item of "pairs" should be a list, not text', "pairs/0"),
        (
            [["2", "4"]],
            'an item of "pairs" should be an integer, not text',
            "pairs/0/1",
        ),
        ([[2, 4]], 'an item of "pairs" should be text, not a number', "pairs/0/0"),
    ],
)
def test_a_pairs_of_the_wrong_type_is_refused_by_the_core_and_the_schema(
    pairs, message, place
):
    doc, timeline, component = document(PLAIN)
    content = with_pairs(doc, pairs)
    assert not jsonschema.Draft202012Validator(tla.schema()).is_valid(content)
    with pytest.raises(tla.UnreadableFile) as caught:
        tla.loads(json.dumps(content).encode())
    assert caught.value.message == message
    assert caught.value.place == (
        f"/timelines/{timeline}/components/{component}/{place}"
    )


@pytest.mark.parametrize("path", WITH_TIME_SIGNATURE, ids=lambda p: p.name)
def test_an_old_files_pairs_of_the_wrong_type_is_refused_at_its_place(path):
    with pytest.raises(tla.UnreadableFile) as caught:
        tla.loads(with_pairs_in_each_time_signature(path, "2/4 + 3/8"))
    assert caught.value.message == '"pairs" should be a list or null, not text'
    assert caught.value.place.startswith("/timelines/")
    assert caught.value.place.endswith("/pairs")


def test_an_empty_list_of_pairs_counts_as_none():
    # As null does: read as a missing key, and left out, so the file loses the
    # line (TimeLineAnnotator/project-management#534).
    doc, timeline, component = document(PLAIN)
    without = tla.canonical_bytes(doc)
    read = tla.loads(json.dumps(with_pairs(doc, [])).encode())
    held = read.timelines[timeline].components[component]
    assert "pairs" not in held.attrs
    assert held.extra == {}
    assert tla.canonical_bytes(read) == without


def test_an_empty_list_of_pairs_given_in_memory_is_left_out():
    doc, timeline, component = document({**PLAIN, "pairs": []})
    written = component_in(tla.canonical_bytes(doc), timeline, component)
    assert "pairs" not in written


def test_an_empty_list_is_none_only_for_pairs():
    # On another kind it is a key the core doesn't know, kept as it is.
    doc, timeline, component = document(
        {"time": 1.0}, kind="bar_line", extra={"pairs": []}
    )
    data = tla.canonical_bytes(doc)
    assert component_in(data, timeline, component)["pairs"] == []
    assert tla.loads(data).timelines[timeline].components[component].extra == {
        "pairs": []
    }


@pytest.mark.parametrize("path", WITH_TIME_SIGNATURE, ids=lambda p: p.name)
def test_an_old_files_empty_pairs_count_as_none(path):
    # No line, and the document id the file without them has (#531, #534).
    plain = tla.loads(path.read_bytes())
    emptied = tla.loads(with_pairs_in_each_time_signature(path, []))
    assert emptied.document_id == plain.document_id
    assert tla.canonical_bytes(emptied) == tla.canonical_bytes(plain)


@pytest.mark.parametrize(
    "pairs",
    [[["2", 4]], [["2"]], [["2", 4, "x"]]],
    ids=["one pair", "a pair too short", "a pair too long"],
)
def test_pairs_of_any_length_are_kept_as_they_are(pairs):
    # A legacy score keeps what TiLiA wrote, unchecked: the right type is all the
    # schema and the core look at, so an open and a save change no byte.
    doc, timeline, component = document(PLAIN)
    content = with_pairs(doc, pairs)
    assert jsonschema.Draft202012Validator(tla.schema()).is_valid(content)
    read = tla.loads(json.dumps(content).encode())
    assert read.timelines[timeline].components[component].attrs["pairs"] == pairs
    data = tla.canonical_bytes(read)
    assert component_in(data, timeline, component)["pairs"] == pairs
    assert tla.canonical_bytes(tla.loads(data)) == data


def test_a_denominator_written_as_1_0_is_read_as_the_integer():
    # An integer written as 1.0 has the right type (FR-051a).
    doc, timeline, component = document(PLAIN)
    content = with_pairs(doc, [["2", 4.0], ["3", 8]])
    read = tla.loads(json.dumps(content).encode())
    attrs = read.timelines[timeline].components[component].attrs
    assert attrs["pairs"] == PAIRS
    assert isinstance(attrs["pairs"][0][1], int)
