"""The format's JSON Schema: shipped in tilia-core, valid Draft 2020-12, and in
agreement with the core (FR-090, FR-091, SC-009).

Every file the tests write is checked against the schema too, by the fixture
`written_files_are_valid` in tests/conftest.py."""

import codecs
import hashlib
import json
from collections import Counter
from importlib.resources import files
from pathlib import Path

import jsonschema
import pytest

from tilia_core import tla
from tilia_core.tla import writer
from tilia_core.tla.model import timeline_kind_from_file

HERE = Path(__file__).parent
GOLDEN_FILES = sorted((HERE / "golden").glob("*.tla"))
EVERY_KIND = HERE / "golden" / "every-kind.tla"
# The files the reader refuses: one for each way a file can be broken.
BROKEN_FILES = sorted((HERE / "broken").glob("*.tla"))
DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
# The schema as the format's specification has it, byte for byte: a change to
# the schema is made there first (TimeLineAnnotator/project-management#179).
SCHEMA_SHA256 = "f12411b5113a467aba9533500891d66c65ef7653b5dea966a996e254a04bcd62"

VALIDATOR = jsonschema.Draft202012Validator(tla.schema())


# The schema itself


def test_the_schema_is_valid_draft_2020_12():
    schema = tla.schema()
    assert schema["$schema"] == DRAFT_2020_12
    validator = jsonschema.validators.validator_for(schema)
    assert validator is jsonschema.Draft202012Validator
    validator.check_schema(schema)


def references(value):
    if isinstance(value, dict):
        if isinstance(value.get("$ref"), str):
            yield value["$ref"]
        for item in value.values():
            yield from references(item)
    elif isinstance(value, list):
        for item in value:
            yield from references(item)


def test_every_reference_in_the_schema_names_one_of_its_definitions():
    # check_schema doesn't follow them.
    schema = tla.schema()
    found = set(references(schema))
    assert found
    assert {ref.replace("#/$defs/", "", 1) for ref in found} <= set(schema["$defs"])


def test_the_schema_is_the_file_the_package_ships():
    # scripts/check_packages.py runs this on the installed wheel, so this also
    # checks that the wheel carries the schema, and carries it unchanged.
    name = f"tla-{tla.FORMAT_VERSION}.schema.json"
    shipped = files("tilia_core.tla").joinpath("schema").joinpath(name)
    assert shipped.is_file()
    assert hashlib.sha256(shipped.read_bytes()).hexdigest() == SCHEMA_SHA256
    assert tla.schema() == json.loads(shipped.read_bytes())


def test_the_schema_names_the_format_version_it_describes():
    schema = tla.schema()
    assert schema["properties"]["version"]["const"] == tla.FORMAT_VERSION
    assert tla.FORMAT_VERSION in schema["title"]


def test_each_call_gives_a_schema_of_its_own():
    # A caller that changes it doesn't change the next caller's.
    mine = tla.schema()
    mine["properties"]["version"]["const"] = "0.0.0"
    del mine["$defs"]["id"]
    again = tla.schema()
    assert again["properties"]["version"]["const"] == tla.FORMAT_VERSION
    assert "id" in again["$defs"]


# Files the writer writes


@pytest.mark.parametrize("path", GOLDEN_FILES, ids=lambda path: path.name)
def test_every_golden_file_is_valid(path):
    VALIDATOR.validate(json.loads(path.read_bytes()))


@pytest.mark.writes_outside_the_schema(
    "checks that the files a test writes are checked"
)
def test_a_file_a_test_writes_is_checked(monkeypatch):
    # The writer itself never writes this: an object with none of the keys.
    monkeypatch.setattr(writer, "_document", lambda doc: {})
    tla.canonical_bytes(tla.new_document())


# Agreement with the core


def strict_json(data):
    """The file's content as a standard JSON parser gives it to a validator,
    or None if it isn't JSON; and whether an object in it repeats a key, which
    such a parser doesn't say: the last value wins."""
    repeated = []

    def pairs(items):
        keys = [key for key, _ in items]
        if len(set(keys)) < len(keys):
            repeated.append(keys)
        return dict(items)

    def constant(name):
        raise ValueError(f"{name} isn't JSON")

    try:
        # One byte-order mark, which the format accepts on reading (FR-061).
        text = data.decode("utf-8-sig")
        content = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, RecursionError):
        return None, False
    return content, bool(repeated)


def entries(value):
    return value.items() if isinstance(value, dict) else ()


def named_nothing(content):
    """The references in `content` that name nothing: a range's row and the
    range it is joined to, a score timeline's score, a measure table, and a
    measure's next measures."""
    timelines = dict(entries(content.get("timelines")))
    scores = content.get("scores") if isinstance(content.get("scores"), list) else []
    score_ids = {score.get("id") for score in scores if isinstance(score, dict)}

    def kind(timeline):
        spelling = timeline.get("kind") if isinstance(timeline, dict) else None
        return timeline_kind_from_file(spelling) if isinstance(spelling, str) else None

    beat_timelines = {key for key, value in timelines.items() if kind(value) == "beat"}
    found = []
    for key, timeline in timelines.items():
        timeline_kind = kind(timeline)
        if not isinstance(timeline_kind, str):
            continue  # a kind the core doesn't know is kept as it is
        components = dict(entries(timeline.get("components")))
        rows = timeline.get("rows") if isinstance(timeline.get("rows"), list) else []
        row_ids = {row.get("id") for row in rows if isinstance(row, dict)}
        refs = [
            (timeline.get("measure_table"), beat_timelines, "measure_table"),
            (timeline.get("score"), score_ids, "score"),
        ]
        for component in components.values():
            if not isinstance(component, dict):
                continue
            if component.get("kind") == "RANGE":
                refs.append((component.get("row_id"), row_ids, "row_id"))
                refs.append((component.get("joined_right"), components, "joined_right"))
            measure = component.get("measure")
            if component.get("kind") == "BEAT" and isinstance(measure, dict):
                following = measure.get("next")
                for item in following if isinstance(following, list) else ():
                    refs.append((item, components, "next"))
        found += [
            f"{name} in {key}"
            for ref, targets, name in refs
            if isinstance(ref, str) and ref not in targets
        ]
    return found


def only_the_core_checks(content, repeated_key):
    """What in a file JSON Schema can't check, and only the core refuses: an
    object that repeats a key, an id used twice and a reference that names
    nothing (FR-090, research R17)."""
    found = ["a repeated key"] if repeated_key else []
    if not isinstance(content, dict):
        return found
    ids = Counter()
    for _, timeline in entries(content.get("timelines")):
        if isinstance(timeline, dict):
            ids.update(key for key, _ in entries(timeline.get("components")))
    ids.update(key for key, _ in entries(content.get("timelines")))
    scores = content.get("scores") if isinstance(content.get("scores"), list) else []
    ids.update(score.get("id") for score in scores if isinstance(score, dict))
    found += [f"the id {key} used twice" for key, n in ids.items() if n > 1]
    return found + named_nothing(content)


def verdicts(data):
    """Whether the core refuses the file, whether the schema does, and what
    in it only the core can check."""
    try:
        tla.loads(data)
        core_refuses = False
    except tla.UnreadableFile:
        core_refuses = True
    content, repeated_key = strict_json(data)
    schema_refuses = content is None or not VALIDATOR.is_valid(content)
    return core_refuses, schema_refuses, only_the_core_checks(content, repeated_key)


def assert_they_agree(data):
    core_refuses, schema_refuses, core_only = verdicts(data)
    if core_only:
        assert core_refuses, f"the core reads a file with {', '.join(core_only)}"
    else:
        assert core_refuses == schema_refuses, (
            f"the core {'refuses' if core_refuses else 'reads'} the file,"
            f" the schema {'refuses' if schema_refuses else 'accepts'} it"
        )


@pytest.mark.parametrize("path", BROKEN_FILES, ids=lambda path: path.name)
def test_the_schema_and_the_core_agree_on_each_broken_file(path):
    assert_they_agree(path.read_bytes())


def golden():
    return json.loads(EVERY_KIND.read_bytes())


def dumped(content):
    return (json.dumps(content, indent=2, ensure_ascii=False) + "\n").encode()


def timeline_of(content, kind):
    return next(tl for tl in content["timelines"].values() if tl["kind"] == kind)


def first_component(timeline):
    return next(iter(timeline["components"].values()))


def changed(change):
    """every-kind.tla's bytes after `change` to its content."""
    content = golden()
    change(content)
    return dumped(content)


def without(*keys):
    """every-kind.tla without the key at the end of `keys`."""

    def change(content):
        parent = content
        for key in keys[:-1]:
            parent = timeline_of(content, key) if key[0].isupper() else parent[key]
        del parent[keys[-1]]

    return changed(change)


def with_unknown_keys(content):
    beat = timeline_of(content, "Beat")
    first = first_component(beat)
    for value in (
        content,
        content["media"],
        beat,
        first,
        first["measure"],
        first["beat_unit"],
        timeline_of(content, "Range")["rows"][0],
        content["scores"][0],
        content["scores"][0]["source"],
    ):
        value["x-note"] = "kept"
    content["timelines"]["019a0000-0000-7000-8000-00000000000a"] = {
        "kind": "Lyrics",
        "ordinal": 99,
        "verses": [{"text": "Leise flehen"}],
    }
    beat["components"]["019a0000-0000-7000-8000-00000000000b"] = {
        "kind": "FERMATA",
        "time": "over the bar",
    }


def with_a_repeated_key(content):
    first_component(timeline_of(content, "Marker"))["label"] = "REPEATED"


def with_two_scores_of_one_id(content):
    content["scores"].append(dict(content["scores"][0]))


def with_warnings(content):
    form = timeline_of(content, "Hierarchy")
    form.setdefault("metadata", {})["vocabulary"] = "LCMA/Form@0.3"
    form["metadata"]["role"] = "time_map"
    timeline_of(content, "Beat")["metadata"]["role"] = "time_map"


AGREEMENT = [
    # The core and the schema both refuse these...
    pytest.param(b"", True, True, id="empty"),
    pytest.param(EVERY_KIND.read_bytes()[:-40], True, True, id="cut short"),
    pytest.param(b'{"title": "Notes"}', True, True, id="not a TiLiA file"),
    pytest.param(
        changed(lambda c: c.update(version="2.0.0")), True, True, id="newer format"
    ),
    pytest.param(
        changed(lambda c: c.update(version="1.0.0-draft.0")),
        True,
        True,
        id="older draft",
    ),
    pytest.param(
        EVERY_KIND.read_bytes().replace(b'"time": 3.0', b'"time": NaN', 1),
        True,
        True,
        id="NaN",
    ),
    pytest.param(without("media"), True, True, id="no media"),
    pytest.param(without("media", "length"), True, True, id="no media length"),
    pytest.param(
        without("Marker", "components"), True, True, id="timeline without components"
    ),
    pytest.param(
        changed(lambda c: c.update(timelines=[])), True, True, id="timelines a list"
    ),
    pytest.param(
        changed(lambda c: first_component(timeline_of(c, "Marker")).update(kind=1)),
        True,
        True,
        id="kind a number",
    ),
    pytest.param(
        changed(lambda c: c["scores"][0].update(content="<mei/>")),
        True,
        True,
        id="score content a string",
    ),
    pytest.param(
        changed(lambda c: c["scores"][0]["content"].append(7)),
        True,
        True,
        id="score line a number",
    ),
    # ...only the core refuses these: JSON Schema can't check them...
    pytest.param(
        changed(with_a_repeated_key).replace(
            b'"label": "REPEATED"', b'"label": "PAC",\n"label": "REPEATED"', 1
        ),
        True,
        False,
        id="repeated key",
    ),
    pytest.param(
        changed(with_two_scores_of_one_id), True, False, id="two scores of one id"
    ),
    # ...and both accept these.
    pytest.param(EVERY_KIND.read_bytes(), False, False, id="golden"),
    pytest.param(
        codecs.BOM_UTF8 + EVERY_KIND.read_bytes().replace(b"\n", b"\r\n"),
        False,
        False,
        id="byte-order mark and CRLF",
    ),
    pytest.param(changed(with_unknown_keys), False, False, id="unknown keys"),
    pytest.param(changed(with_warnings), False, False, id="warnings only"),
]


@pytest.mark.parametrize("data, core_refuses, schema_refuses", AGREEMENT)
def test_the_schema_and_the_core_agree(data, core_refuses, schema_refuses):
    assert verdicts(data)[:2] == (core_refuses, schema_refuses)
    assert_they_agree(data)


def key_of(content, kind):
    return next(key for key, tl in content["timelines"].items() if tl["kind"] == kind)


def test_what_only_the_core_checks_is_found():
    # The agreement lets the core alone refuse these: so each must be found,
    # and nothing else taken for one.
    content = golden()
    assert only_the_core_checks(content, False) == []
    assert only_the_core_checks(content, True) == ["a repeated key"]
    form = timeline_of(content, "Hierarchy")
    unit_id = next(iter(form["components"]))
    timeline_of(content, "Marker")["components"][unit_id] = {"kind": "MARKER"}
    first_component(timeline_of(content, "Range")).update(
        row_id="gone", joined_right="gone"
    )
    timeline_of(content, "Score")["score"] = "no score"
    form["measure_table"] = unit_id  # a component's id, not a beat timeline's
    first_component(timeline_of(content, "Beat"))["measure"]["next"] = ["gone"]
    ranges, score, hierarchy, beats = (
        key_of(content, kind) for kind in ("Range", "Score", "Hierarchy", "Beat")
    )
    assert sorted(only_the_core_checks(content, False)) == sorted(
        [
            f"the id {unit_id} used twice",
            f"row_id in {ranges}",
            f"joined_right in {ranges}",
            f"score in {score}",
            f"measure_table in {hierarchy}",
            f"next in {beats}",
        ]
    )
