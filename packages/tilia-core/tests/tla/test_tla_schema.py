"""The format's JSON Schema: shipped in tilia-core, valid Draft 2020-12, and in
agreement with the core (FR-090, FR-091, SC-009).

Every file the tests write is checked against the schema too, by the fixture
`written_files_are_valid` in tests/conftest.py."""

import codecs
import hashlib
import json
import subprocess
import sys
import unicodedata
from collections import Counter
from importlib.resources import files
from pathlib import Path

import jsonschema
import pytest

from tilia_core import tla
from tilia_core.tla import writer
from tilia_core.tla.model import timeline_kind_from_current_file

HERE = Path(__file__).parent
GOLDEN_FILES = sorted((HERE / "golden").glob("*.tla"))
EVERY_KIND = HERE / "golden" / "every-kind.tla"
# The files the reader refuses: one for each way a file can be broken.
BROKEN_FILES = sorted((HERE / "broken").glob("*.tla"))
DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
# The schema as the format's specification has it, byte for byte: a change to
# the schema is made there first (TimeLineAnnotator/project-management#179).
SCHEMA_SHA256 = "2fddc2aa6b54d24121163a2f84042216119096e58ba8b7673c8a99d9d3939de2"

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


def shipped_schema():
    """The schema's file, as the installed package has it."""
    name = f"tla-{tla.FORMAT_VERSION}.schema.json"
    return files("tilia_core.tla").joinpath("schemas").joinpath(name)


def test_the_schema_is_the_file_the_package_ships():
    # scripts/check_packages.py runs this on the installed wheel, so this also
    # checks that the wheel carries the schema, and carries it unchanged.
    shipped = shipped_schema()
    assert shipped.is_file()
    assert hashlib.sha256(shipped.read_bytes()).hexdigest() == SCHEMA_SHA256
    assert tla.schema() == json.loads(shipped.read_bytes())


IMPORT_EVERY_FOLDER = """
import json
from importlib.resources import files

from tilia_core import tla

public = {name: getattr(tla, name) for name in tla.__all__}
for folder in files("tilia_core.tla").iterdir():
    if folder.is_dir() and not folder.name.startswith("__"):
        files(f"tilia_core.tla.{folder.name}")
print(json.dumps([name for name in public if getattr(tla, name) is not public[name]]))
print(json.dumps(tla.schema()))
"""


def test_importing_a_folder_of_tla_leaves_schema_a_function(tmp_path):
    # importlib.resources imports a folder by its dotted name, and a folder of
    # data, without an __init__.py, becomes a namespace package and an
    # attribute of tla: a folder named schema would replace tla.schema. Run in
    # a process of its own, so that it can't change tla for the other tests.
    result = subprocess.run(
        [sys.executable, "-c", IMPORT_EVERY_FOLDER],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    lines = result.stdout.splitlines()
    assert lines, result.stderr
    assert json.loads(lines[0]) == [], "replaced by a folder of the same name"
    assert result.returncode == 0, result.stderr
    assert json.loads(lines[1]) == json.loads(shipped_schema().read_bytes())


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


@pytest.mark.writes_outside_the_schema(
    "checks that the files a test writes are checked"
)
def test_a_file_written_once_checked_is_checked_too(monkeypatch):
    # checked_bytes gives what write writes. With the reader's checks off, it
    # gives an object with none of the keys.
    monkeypatch.setattr(writer, "_document", lambda doc: {})
    monkeypatch.setattr(writer, "check", lambda *args, **kwargs: None)
    writer.checked_bytes(tla.new_document(), path="piece.tla")


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


def nfc(value):
    return unicodedata.normalize("NFC", value) if isinstance(value, str) else value


def known_timelines(content):
    """The timelines of kinds the core knows, spelt exactly as the writer
    writes them, by id, with their kinds. What a timeline of another kind
    holds is kept as it is, and never looked at (FR-015)."""
    found = {}
    for key, timeline in entries(content.get("timelines")):
        spelling = timeline.get("kind") if isinstance(timeline, dict) else None
        if isinstance(spelling, str):
            kind = timeline_kind_from_current_file(spelling)
            if isinstance(kind, str):  # not an UnknownKind
                found[key] = (kind, timeline)
    return found


def named_nothing(content):
    """The references in `content` that name nothing: a range's row and the
    range it is joined to, a score timeline's score, a measure table, and a
    measure's next measures. A component is followed only in a timeline that
    holds its kind: elsewhere it is kept as it is."""
    timelines = known_timelines(content)
    scores = content.get("scores") if isinstance(content.get("scores"), list) else []
    score_ids = {score.get("id") for score in scores if isinstance(score, dict)}
    beat_timelines = {key for key, (kind, _) in timelines.items() if kind == "beat"}
    found = []
    for key, (timeline_kind, timeline) in timelines.items():
        components = dict(entries(timeline.get("components")))
        rows = timeline.get("rows") if isinstance(timeline.get("rows"), list) else []
        # Compared as the reader gives them: in NFC.
        row_ids = {nfc(row.get("id")) for row in rows if isinstance(row, dict)}
        refs = [(timeline.get("measure_table"), beat_timelines, "measure_table")]
        if timeline_kind == "score":
            refs.append((timeline.get("score"), score_ids, "score"))
        for component in components.values():
            if not isinstance(component, dict):
                continue
            if timeline_kind == "range" and component.get("kind") == "RANGE":
                refs.append((nfc(component.get("row_id")), row_ids, "row_id"))
                refs.append((component.get("joined_right"), components, "joined_right"))
            measure = component.get("measure")
            if (
                timeline_kind == "beat"
                and component.get("kind") == "BEAT"
                and isinstance(measure, dict)
            ):
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
    object that repeats a key, an id used twice in the file or a row's in its
    timeline, and a reference that names nothing (FR-090, research R17)."""
    found = ["a repeated key"] if repeated_key else []
    if not isinstance(content, dict):
        return found
    timelines = known_timelines(content)
    ids = Counter(key for key, _ in entries(content.get("timelines")))
    for _, timeline in timelines.values():
        ids.update(key for key, _ in entries(timeline.get("components")))
    scores = content.get("scores") if isinstance(content.get("scores"), list) else []
    ids.update(score.get("id") for score in scores if isinstance(score, dict))
    found += [f"the id {key} used twice" for key, n in ids.items() if n > 1]
    for key, (kind, timeline) in timelines.items():
        rows = timeline.get("rows")
        if kind != "range" or not isinstance(rows, list):
            continue
        row_ids = Counter(nfc(row.get("id")) for row in rows if isinstance(row, dict))
        found += [
            f"the row id {row_id} used twice in {key}"
            for row_id, n in row_ids.items()
            if isinstance(row_id, str) and n > 1
        ]
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


def with_two_rows_of_one_id(content):
    rows = timeline_of(content, "Range")["rows"]
    rows.append(dict(rows[0], name="Another"))


def with_two_rows_of_one_id_in_nfc(content):
    # Row ids are any text, compared as the reader gives them: in NFC.
    ranges = timeline_of(content, "Range")
    old = ranges["rows"][0]["id"]
    ranges["rows"][0]["id"] = "café"
    ranges["rows"].append({"id": "café", "name": "Another"})
    for component in ranges["components"].values():
        if component["row_id"] == old:
            component["row_id"] = "café"


def with_a_row_named_in_nfd(content):
    ranges = timeline_of(content, "Range")
    old = ranges["rows"][0]["id"]
    ranges["rows"][0]["id"] = "café"
    for component in ranges["components"].values():
        if component["row_id"] == old:
            component["row_id"] = "café"


def with_a_kind_in_another_letter_case(content):
    # "range" is a kind the core doesn't know: what it holds is kept as it is.
    ranges = timeline_of(content, "Range")
    first_component(ranges)["row_id"] = "gone"
    ranges["kind"] = "range"


def with_a_range_in_a_marker_timeline(content):
    # Kept as it is, with a warning: its row isn't looked for.
    misplaced = dict(first_component(timeline_of(content, "Range")), row_id="gone")
    del misplaced["joined_right"]
    markers = timeline_of(content, "Marker")["components"]
    markers["019a0000-0000-7000-8000-00000000000c"] = misplaced


def with_an_unknown_timeline_repeating_an_id(content):
    # What a timeline of an unknown kind holds is kept as it is.
    content["timelines"]["019a0000-0000-7000-8000-00000000000d"] = {
        "kind": "Lyrics",
        "ordinal": 99,
        "components": dict(timeline_of(content, "Marker")["components"]),
    }


def first_marker(content):
    return first_component(timeline_of(content, "Marker"))


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
    pytest.param(
        changed(lambda c: c.update(version=c["version"] + "+build.5")),
        True,
        True,
        id="build metadata",
    ),
    pytest.param(
        changed(lambda c: first_marker(c).update(time=None)),
        True,
        True,
        id="null on a required key",
    ),
    pytest.param(
        changed(lambda c: c["scores"][0].update(source=None)),
        True,
        True,
        id="MEI score's null source",
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
    pytest.param(
        changed(with_two_rows_of_one_id), True, False, id="two rows of one id"
    ),
    pytest.param(
        changed(with_two_rows_of_one_id_in_nfc),
        True,
        False,
        id="two rows of one id in NFC",
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
    pytest.param(
        changed(lambda c: first_marker(c).update(label=None)),
        False,
        False,
        id="null on a key that isn't required",
    ),
    pytest.param(
        changed(lambda c: c["scores"][0].update(license=None)),
        False,
        False,
        id="MEI score's null licence",
    ),
    pytest.param(
        changed(
            lambda c: c["scores"][0].update(
                format="musicxml", source=None, license=None
            )
        ),
        False,
        False,
        id="null source and licence on a score of an unknown format",
    ),
    pytest.param(
        changed(lambda c: first_component(timeline_of(c, "Hierarchy")).update(level=0)),
        False,
        False,
        id="level below 1",
    ),
    pytest.param(
        changed(lambda c: timeline_of(c, "Marker").update(ordinal=0)),
        False,
        False,
        id="ordinal below 1",
    ),
    pytest.param(
        changed(lambda c: c.update(time_unit="frames")),
        False,
        False,
        id="time unit the schema doesn't list",
    ),
    pytest.param(
        changed(lambda c: timeline_of(c, "Marker").update(ordinal=5.0)),
        False,
        False,
        id="integer written as 5.0",
    ),
    pytest.param(
        changed(with_a_kind_in_another_letter_case),
        False,
        False,
        id="timeline kind in another letter case",
    ),
    pytest.param(
        changed(with_a_range_in_a_marker_timeline),
        False,
        False,
        id="range in a marker timeline",
    ),
    pytest.param(
        changed(with_an_unknown_timeline_repeating_an_id),
        False,
        False,
        id="unknown timeline repeating an id",
    ),
    pytest.param(changed(with_a_row_named_in_nfd), False, False, id="row named in NFD"),
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
    rows = timeline_of(content, "Range")["rows"]
    rows.append(dict(rows[1], name="Another"))
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
            f"the row id {rows[1]['id']} used twice in {ranges}",
            f"row_id in {ranges}",
            f"joined_right in {ranges}",
            f"score in {score}",
            f"measure_table in {hierarchy}",
            f"next in {beats}",
        ]
    )
