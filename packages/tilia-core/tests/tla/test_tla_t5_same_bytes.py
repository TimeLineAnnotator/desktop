"""T5's third test: the same document gives the same bytes on every system,
under every supported Python, from any working folder and whoever runs it.

CI runs these on Windows, macOS and Linux with each supported Python; the
golden files are the bytes every one of them must write."""

import codecs
import importlib.util
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

from tilia_core import tla
from tilia_core.tla import layout
from tilia_core.tla.model import COMPONENT_KINDS, TIMELINE_KINDS

GOLDEN = Path(__file__).parent / "golden"
GOLDEN_FILES = sorted(GOLDEN.glob("*.tla"))
EVERY_KIND = GOLDEN / "every-kind.tla"

# A \u escape, not a backslash written as \\ followed by "u".
ESCAPE = re.compile(r"(?<!\\)(?:\\\\)*\\u([0-9a-fA-F]{4})")


@pytest.fixture(params=GOLDEN_FILES, ids=lambda path: path.name)
def golden(request):
    return request.param


def assert_one_form(data):
    assert not data.startswith(codecs.BOM_UTF8)
    assert b"\r" not in data
    assert data.endswith(b"}\n") and not data.endswith(b"\n\n")
    text = data.decode("utf-8")
    for match in ESCAPE.finditer(text):
        assert not chr(int(match.group(1), 16)).isprintable(), match.group()
    for line in text.split("\n"):
        indent = len(line) - len(line.lstrip(" "))
        assert indent % 2 == 0 and not line[indent:].startswith("\t"), line
        assert line == line.rstrip(), line


def test_the_writer_writes_one_form(golden):
    assert_one_form(tla.canonical_bytes(tla.read(golden)))


def test_text_is_written_as_it_is_and_escaped_only_where_json_requires_it():
    doc = tla.read(EVERY_KIND)
    form = next(tl for tl in doc.timelines.values() if tl.name == "Form")
    labels = [
        "bell \x07, tab \t, line\nbreak",
        'quote ", backslash \\ and a written \\u00e9',
        "    ​ é ü 🎵",
    ]
    for component, label in zip(
        list(form.components.values())[:3], labels, strict=True
    ):
        component.attrs["label"] = label
    data = tla.canonical_bytes(doc)
    assert_one_form(data)
    assert '"    ​ é ü 🎵"'.encode() in data
    assert b'"bell \\u0007, tab \\t, line\\nbreak"' in data
    assert b'"quote \\", backslash \\\\ and a written \\\\u00e9"' in data
    again = tla.loads(data)
    form = again.timelines[form.id]
    assert [c.attrs["label"] for c in form.components.values()][:3] == labels


def test_a_lone_surrogate_is_written_as_an_escape_and_reads_back():
    # A label cut inside an emoji, which json.loads accepts from an escape.
    doc = tla.read(EVERY_KIND)
    doc.metadata["title"] = "cut \ud83c"
    data = tla.canonical_bytes(doc)
    assert b'"title": "cut \\ud83c"' in data
    assert tla.loads(data).metadata["title"] == "cut \ud83c"


@pytest.mark.parametrize("hash_seed", ["0", "4242"])
def test_another_folder_and_user_give_the_same_bytes(golden, tmp_path, hash_seed):
    home = tmp_path / "home of someone else"
    home.mkdir()
    folder = tmp_path / "elsewhere"
    folder.mkdir()
    env = {
        **os.environ,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "USER": "someone-else",
        "PYTHONHASHSEED": hash_seed,
    }
    script = (
        "import sys\n"
        "from tilia_core import tla\n"
        "sys.stdout.buffer.write(tla.canonical_bytes(tla.read(sys.argv[1])))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(golden)],
        cwd=folder,
        env=env,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert result.stdout == golden.read_bytes()


def test_another_folder_in_the_same_process_gives_the_same_bytes(
    golden, tmp_path, monkeypatch
):
    doc = tla.read(golden)
    monkeypatch.chdir(tmp_path)
    for name in ("HOME", "USERPROFILE", "USER"):
        monkeypatch.setenv(name, str(tmp_path))
    assert tla.canonical_bytes(doc) == golden.read_bytes()
    assert tla.canonical_bytes(tla.read(golden)) == golden.read_bytes()


def test_the_golden_files_are_what_make_golden_writes():
    spec = importlib.util.spec_from_file_location(
        "make_golden", GOLDEN / "make_golden.py"
    )
    make_golden = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(make_golden)
    written = make_golden.golden_bytes()
    assert sorted(written) == [path.name for path in GOLDEN_FILES]
    for name, data in written.items():
        assert (GOLDEN / name).read_bytes() == data, f"run make_golden.py: {name}"


SCHEMA = json.loads(
    (
        Path(layout.__file__).parent
        / "schema"
        / f"tla-{tla.FORMAT_VERSION}.schema.json"
    ).read_bytes()
)


def branches(definition, key):
    for branch in definition["allOf"]:
        test = branch["if"]["properties"][key]
        for value in test.get("enum", [test.get("const")]):
            yield value, branch["then"]


def test_the_writers_key_orders_are_the_schemas():
    # The writer's tables give the order; the schema lists the same keys in it.
    defs = SCHEMA["$defs"]
    assert tuple(SCHEMA["properties"]) == layout.TOP_LEVEL
    assert tuple(SCHEMA["properties"]["media"]["properties"]) == layout.MEDIA
    base = tuple(defs["timeline_base"]["properties"])
    assert base == layout.TIMELINE_BEFORE + layout.TIMELINE_AFTER
    timelines = dict(branches(defs["timeline"], "kind"))
    assert sorted(timelines) == sorted(TIMELINE_KINDS.values())
    for kind, spelling in TIMELINE_KINDS.items():
        own = tuple(
            k for k in timelines[spelling].get("properties", {}) if k not in base
        )
        assert own == layout.TIMELINE_OWN[kind], kind
    components = dict(branches(defs["component"], "kind"))
    assert sorted(components) == sorted(COMPONENT_KINDS.values())
    for kind, spelling in COMPONENT_KINDS.items():
        attributes = tuple(components[spelling].get("properties", ()))
        if kind in layout.LEGACY_SCORE_COMPONENTS:
            assert attributes == ()
        else:
            assert attributes == layout.COMPONENT_ATTRIBUTES[kind], kind
    assert tuple(defs["measure"]["properties"]) == layout.MEASURE
    assert tuple(defs["beat_unit"]["properties"]) == layout.BEAT_UNIT
    rows = timelines["Range"]["properties"]["rows"]["items"]["properties"]
    assert tuple(rows) == layout.RANGE_ROW
    scores = dict(branches(defs["score"], "format"))
    for format, keys in layout.SCORES.items():
        known = {*defs["score"]["properties"], *scores[format]["properties"]}
        assert known == set(keys), format
    assert tuple(scores["mei"]["properties"]["source"]["properties"]) == (
        layout.SCORE_SOURCE
    )


def derived_names(value):
    if isinstance(value, dict):
        if isinstance(value.get("x-default-from"), str):
            yield value["x-default-from"]
        for item in value.values():
            yield from derived_names(item)
    elif isinstance(value, list):
        for item in value:
            yield from derived_names(item)


def test_every_default_the_schema_derives_is_implemented():
    shapes = [
        *layout.TIMELINE_SHAPES.values(),
        *layout.COMPONENT_SHAPES.values(),
        layout.MEASURE_SHAPE,
        layout.BEAT_UNIT_SHAPE,
        layout.RANGE_ROW_SHAPE,
        *layout.SCORE_SHAPES.values(),
    ]
    by_name = {
        layout.PREVIOUS_NUMBER_PLUS_ONE,
        layout.NUMBER_AS_TEXT,
        layout.TIMELINE_MEASURE_SOURCE,
    }
    found = set()
    for shape in shapes:
        for name in shape.derived.values():
            # From a key of the same object, or by name, for a measure's mark.
            assert name in shape.keys or (
                shape is layout.MEASURE_SHAPE and name in by_name
            )
            found.add(name)
    assert found == set(derived_names(SCHEMA))


def test_the_defaults_are_the_schemas():
    marker = layout.COMPONENT_SHAPES["marker"]
    assert marker.defaults == {"comments": "", "label": "", "color": None}
    assert marker.always == {"kind", "time"}
    assert marker.left_out_empty == {"metadata"}
    assert layout.COMPONENT_SHAPES["hierarchy"].derived == {
        "pre_start": "start",
        "post_end": "end",
    }
    assert layout.TIMELINE_SHAPES["beat"].defaults == {
        "name": "",
        "is_visible": True,
        "beat_pattern": "4",
        "show_time_signatures": True,
        "measure_source": "tapped",
        "measure_table": None,
    }
    # Left out at its default, NOASSERTION, like any key.
    assert layout.SCORE_SHAPES["mei"].defaults == {"license": "NOASSERTION"}
    assert layout.SCORE_SHAPES["mei"].always == {"id", "format", "source", "content"}


def test_no_key_is_both_required_and_given_a_default():
    # A missing key always means its default, so the schema never requires a
    # key it gives one; required keys are among those always written.
    shapes = [
        layout.TOP_SHAPE,
        layout.MEDIA_SHAPE,
        *layout.TIMELINE_SHAPES.values(),
        *layout.COMPONENT_SHAPES.values(),
        layout.UNKNOWN_COMPONENT,
        layout.MEASURE_SHAPE,
        layout.BEAT_UNIT_SHAPE,
        layout.RANGE_ROW_SHAPE,
        *layout.SCORE_SHAPES.values(),
        layout.UNKNOWN_SCORE,
        layout.SCORE_SOURCE_SHAPE,
    ]
    for shape in shapes:
        assert shape.always.isdisjoint(shape.defaults), shape.keys
        assert shape.always.isdisjoint(shape.derived), shape.keys


@pytest.mark.skipif(
    unicodedata.unidata_version != "13.0.0",
    reason="needs Unicode 13.0 (Python 3.10), where later characters are unassigned",
)
def test_the_golden_files_hold_no_character_added_after_unicode_13(golden):
    # NFC is the running Python's: a character it doesn't know yet can normalise
    # differently on another Python, so the golden files hold none. Python 3.10
    # has Unicode 13.0, and CI runs it.
    text = golden.read_text("utf-8")
    later = sorted({c for c in text if unicodedata.category(c) == "Cn"})
    assert later == []
