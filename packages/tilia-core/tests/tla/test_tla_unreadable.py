"""Files the reader refuses: each with a message for users, its place in the
file as a JSON Pointer and, where it can, its line; and documents the writer
refuses, because the reader would refuse what it wrote."""

import copy
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import pytest

from tilia_core import tla
from tilia_core.tla import layout, writer
from tilia_core.tla.parse import lines_of, pointer

BROKEN = Path(__file__).parent / "broken"
BROKEN_FILES = sorted(BROKEN.glob("*.tla"))


def _load_make_broken():
    spec = importlib.util.spec_from_file_location(
        "make_broken", BROKEN / "make_broken.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


make_broken = _load_make_broken()
IDS = make_broken.IDS


def place(template):
    return template.format(**IDS)


def refusal(data, path=None):
    with pytest.raises(tla.UnreadableFile) as error:
        tla.loads(data, path=path)
    return error.value


def base_bytes():
    return make_broken.text_of(make_broken.base()).encode("utf-8")


def base_document():
    return tla.loads(base_bytes())


def named(doc, name):
    return next(tl for tl in doc.timelines.values() if tl.name == name)


# The broken files


FORM = IDS["form"]
COMPONENT = "/timelines/{cadences}/components/{cadence}"
SECTION = "/timelines/{form}/components/{section}"
BEAT_1 = "/timelines/{beats}/components/{beat_1}"
MELODY = "/timelines/{texture}/components/{melody_1}"

EXPECTED = {
    "not-json.tla": ("not valid JSON (Expecting ',' delimiter)", None, 6),
    "cut-short.tla": ("not valid JSON (Unterminated string)", None, 49),
    "error-page.tla": ("not valid JSON (Expecting value)", None, 1),
    "second-byte-order-mark.tla": (
        "not valid JSON (a byte-order mark out of place)",
        None,
        1,
    ),
    "empty-file.tla": ("empty file", None, None),
    "another-program.tla": ("not a TiLiA file", None, None),
    "repeated-key.tla": (
        '"label" appears twice in one object',
        SECTION + "/label",
        50,
    ),
    "newer-format.tla": ("written by a newer TiLiA (format 2.0.0)", "/version", 3),
    "older-draft.tla": (
        "a draft of the format (1.0.0-draft.0): convert it again from its sources",
        "/version",
        3,
    ),
    "component-without-id.tla": (
        "a component has no id",
        "/timelines/{cadences}/components/",
        60,
    ),
    "id-not-a-uuid.tla": (
        "a component's id isn't a UUID: \"7\"",
        "/timelines/{cadences}/components/7",
        60,
    ),
    "id-in-two-timelines.tla": (
        'two components have the id "{section}"',
        "/timelines/{cadences}/components/{section}",
        60,
    ),
    "time-as-text.tla": (
        '"time" should be a number, not text',
        COMPONENT + "/time",
        62,
    ),
    "level-missing.tla": ('"level" is missing', SECTION + "/level", 44),
    "time-null.tla": ('"time" should be a number, not null', COMPONENT + "/time", 62),
    "unknown-kind-ordinal-as-text.tla": (
        '"ordinal" should be an integer, not text',
        "/timelines/{form}/ordinal",
        38,
    ),
    "metadata-not-an-object.tla": (
        '"metadata" should be an object or null, not a list',
        "/timelines/{form}/metadata",
        40,
    ),
    "score-without-lines.tla": (
        "the score's content has no lines",
        "/scores/0/content",
        111,
    ),
    "row-id-twice.tla": (
        'two rows have the id "aZ3k9P"',
        "/timelines/{texture}/rows/1/id",
        78,
    ),
    "row-named-nowhere.tla": (
        'a range names row "Qm7x2L", which its timeline doesn\'t have',
        MELODY + "/row_id",
        83,
    ),
    "joined-to-nothing.tla": (
        'a range is joined to "{nothing}", which its timeline doesn\'t have',
        MELODY + "/joined_right",
        84,
    ),
    "score-named-nowhere.tla": (
        'a score timeline names the score "{nothing}", which the file doesn\'t have',
        "/timelines/{score_timeline}/score",
        99,
    ),
    "score-measure-table-named-nowhere.tla": (
        'a timeline names "{nothing}" as its measure table, which isn\'t a beat'
        " timeline of the file",
        "/timelines/{score_timeline}/measure_table",
        100,
    ),
    "imported-measure-table-named-nowhere.tla": (
        'a timeline names "{nothing}" as its measure table, which isn\'t a beat'
        " timeline of the file",
        "/timelines/{cadences}/measure_table",
        58,
    ),
    "measure-table-not-a-beat-timeline.tla": (
        'a timeline names "{form}" as its measure table, which isn\'t a beat'
        " timeline of the file",
        "/timelines/{cadences}/measure_table",
        58,
    ),
    "next-named-nowhere.tla": (
        'a measure is followed by "{nothing}", which isn\'t a beat of its timeline',
        BEAT_1 + "/measure/next/0",
        25,
    ),
    "first-beat-without-mark.tla": (
        'the first beat of the timeline "Beats" has no measure mark',
        BEAT_1,
        20,
    ),
}


@pytest.fixture(params=BROKEN_FILES, ids=lambda path: path.name)
def broken(request):
    return request.param


def test_every_broken_file_has_its_expected_refusal():
    assert sorted(EXPECTED) == [path.name for path in BROKEN_FILES]


def test_the_broken_files_are_what_make_broken_writes():
    written = make_broken.broken_bytes()
    assert sorted(written) == [path.name for path in BROKEN_FILES]
    for name, data in written.items():
        assert (BROKEN / name).read_bytes() == data, f"run make_broken.py: {name}"


def test_the_readme_lists_every_broken_file():
    readme = (BROKEN / "README.md").read_text("utf-8")
    listed = re.findall(r"^\| `([^`]+\.tla)` \|", readme, re.MULTILINE)
    assert listed == sorted(EXPECTED)


def test_the_file_the_broken_ones_come_from_reads():
    doc = base_document()
    assert doc.warnings == []
    assert tla.canonical_bytes(doc) == base_bytes()


def test_each_broken_file_is_refused_with_its_message_place_and_line(broken):
    message, where, line = EXPECTED[broken.name]
    with pytest.raises(tla.UnreadableFile) as error:
        tla.read(broken)
    assert error.value.message == place(message)
    assert error.value.place == (None if where is None else place(where))
    assert error.value.line == line
    assert error.value.path == broken


def test_loads_refuses_as_read_does(broken):
    with pytest.raises(tla.UnreadableFile) as from_file:
        tla.read(broken)
    error = refusal(broken.read_bytes())
    assert (error.message, error.place, error.line) == (
        from_file.value.message,
        from_file.value.place,
        from_file.value.line,
    )
    assert error.path is None


def test_the_error_reads_as_a_sentence_with_the_file_and_line():
    with pytest.raises(tla.UnreadableFile) as error:
        tla.read(BROKEN / "time-as-text.tla")
    assert str(error.value) == (
        'time-as-text.tla, line 62: "time" should be a number, not text'
    )


def test_an_error_without_a_line_names_the_file():
    with pytest.raises(tla.UnreadableFile) as error:
        tla.read(BROKEN / "empty-file.tla")
    assert str(error.value) == "empty-file.tla: empty file"


@pytest.mark.parametrize(
    "name", ["time-as-text.tla", "row-named-nowhere.tla", "level-missing.tla"]
)
def test_the_line_is_found_in_a_file_laid_out_otherwise(name):
    # Keys and values on lines of their own, as a hand might lay them out.
    data = (BROKEN / name).read_bytes()
    content = json.loads(data)
    text = json.dumps(content, indent="\t", separators=(",\n", ":\n"))
    error = refusal(text.encode())
    message, where, _ = EXPECTED[name]
    assert (error.message, error.place) == (place(message), place(where))
    key = place(where).rsplit("/", 1)[1]
    if name == "level-missing.tla":
        key = IDS["section"]  # the component that has no level
    assert text.split("\n")[error.line - 1].strip() == f'"{key}":'


def test_the_line_is_found_after_a_byte_order_mark_and_in_crlf():
    data = (BROKEN / "time-as-text.tla").read_bytes()
    error = refusal(b"\xef\xbb\xbf" + data.replace(b"\n", b"\r\n"))
    assert error.line == 62


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_a_file_that_cant_be_read_gives_the_systems_error(tmp_path):
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root reads any file")
    path = tmp_path / "locked.tla"
    path.write_bytes(base_bytes())
    path.chmod(0)
    try:
        with pytest.raises(PermissionError):
            tla.read(path)
    finally:
        path.chmod(0o600)


def test_a_file_that_isnt_there_gives_the_systems_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        tla.read(tmp_path / "missing.tla")


# Each refusal, one at a time


def edited(change):
    content = copy.deepcopy(make_broken.base())
    change(content)
    return make_broken.text_of(content).encode("utf-8")


def timeline(content, name):
    return content["timelines"][IDS[name]]


def component(content, name, of):
    return timeline(content, of)["components"][IDS[name]]


@pytest.mark.parametrize(
    "change, where, message",
    [
        (
            lambda c: c.update(document_id="piece-1"),
            "/document_id",
            '"document_id" isn\'t a UUID: "piece-1"',
        ),
        (
            lambda c: c.update(document_id=IDS["document"].upper()),
            "/document_id",
            f'"document_id" isn\'t a UUID: "{IDS["document"].upper()}"',
        ),
        (
            lambda c: c.update(
                timelines=make_broken.renamed(c["timelines"], IDS["form"], "2")
            ),
            "/timelines/2",
            "a timeline's id isn't a UUID: \"2\"",
        ),
        (
            lambda c: c["scores"][0].update(id="a"),
            "/scores/0/id",
            '"id" isn\'t a UUID: "a"',
        ),
        (
            lambda c: c["scores"][0].update(id=IDS["form"]),
            "/scores/0/id",
            'a timeline and a score have the id "{form}"',
        ),
        (
            lambda c: c["scores"].append({**c["scores"][0], "content": [""]}),
            "/scores/1/id",
            'two scores have the id "{score}"',
        ),
        (
            lambda c: timeline(c, "form").update(ordinal="2"),
            "/timelines/{form}/ordinal",
            '"ordinal" should be an integer, not text',
        ),
        (
            lambda c: timeline(c, "form").update(ordinal=2.5),
            "/timelines/{form}/ordinal",
            '"ordinal" should be an integer, not a number',
        ),
        (
            lambda c: timeline(c, "form").update(is_visible=1),
            "/timelines/{form}/is_visible",
            '"is_visible" should be true or false or null, not a number',
        ),
        (
            lambda c: timeline(c, "form").pop("height"),
            "/timelines/{form}/height",
            '"height" is missing',
        ),
        (
            lambda c: timeline(c, "texture").pop("rows"),
            "/timelines/{texture}/rows",
            '"rows" is missing',
        ),
        (
            lambda c: timeline(c, "texture")["rows"][0].pop("name"),
            "/timelines/{texture}/rows/0/name",
            '"name" is missing',
        ),
        (
            lambda c: timeline(c, "texture")["rows"].append("Bass"),
            "/timelines/{texture}/rows/1",
            'an item of "rows" should be an object, not text',
        ),
        (
            lambda c: component(c, "section", of="form").update(level="1"),
            SECTION + "/level",
            '"level" should be an integer, not text',
        ),
        (
            lambda c: component(c, "section", of="form").update(level=True),
            SECTION + "/level",
            '"level" should be an integer, not true or false',
        ),
        (
            lambda c: component(c, "section", of="form").update(level=None),
            SECTION + "/level",
            '"level" should be an integer, not null',
        ),
        (
            lambda c: component(c, "cadence", of="cadences").update(time=None),
            COMPONENT + "/time",
            '"time" should be a number, not null',
        ),
        (
            lambda c: component(c, "section", of="form").update(color=5),
            SECTION + "/color",
            '"color" should be text or null, not a number',
        ),
        (
            lambda c: component(c, "section", of="form").update(metadata={"tags": 1}),
            SECTION + "/metadata/tags",
            '"tags" should be text or a list, not a number',
        ),
        (
            lambda c: component(c, "section", of="form").update(
                metadata={"tags": ["a", 2]}
            ),
            SECTION + "/metadata/tags/1",
            'an item of "tags" should be text, not a number',
        ),
        (
            lambda c: component(c, "section", of="form").pop("kind"),
            SECTION + "/kind",
            '"kind" is missing',
        ),
        (
            lambda c: component(c, "section", of="form").update(kind=["HIERARCHY"]),
            SECTION + "/kind",
            '"kind" should be text, not a list',
        ),
        (
            lambda c: timeline(c, "beats")["components"][IDS["beat_1"]].update(
                measure={"number": "1"}
            ),
            "/timelines/{beats}/components/{beat_1}/measure/number",
            '"number" should be an integer or null, not text',
        ),
        (
            lambda c: timeline(c, "beats")["components"][IDS["beat_1"]].update(
                measure={"next": ["b2"]}
            ),
            "/timelines/{beats}/components/{beat_1}/measure/next/0",
            'an item of "next" isn\'t a UUID: "b2"',
        ),
        (
            lambda c: timeline(c, "beats")["components"][IDS["beat_1"]][
                "beat_unit"
            ].pop("units"),
            "/timelines/{beats}/components/{beat_1}/beat_unit/units",
            '"units" is missing',
        ),
        (
            lambda c: component(c, "melody_1", of="texture").update(
                joined_right="melody_2"
            ),
            MELODY + "/joined_right",
            '"joined_right" isn\'t a UUID: "melody_2"',
        ),
        (
            lambda c: timeline(c, "form").update(kind="Lyrics", ordinal="x"),
            "/timelines/{form}/ordinal",
            '"ordinal" should be an integer, not text',
        ),
        (
            lambda c: timeline(c, "form").update(kind="Lyrics", ordinal=1.5),
            "/timelines/{form}/ordinal",
            '"ordinal" should be an integer, not a number',
        ),
        (
            lambda c: timeline(c, "form").update(kind="Lyrics")
            or timeline(c, "form").pop("ordinal"),
            "/timelines/{form}/ordinal",
            '"ordinal" is missing',
        ),
        (
            lambda c: timeline(c, "form").update(kind="Lyrics", ordinal=None),
            "/timelines/{form}/ordinal",
            '"ordinal" should be an integer, not null',
        ),
        (
            lambda c: timeline(c, "form").update(kind="Lyrics", name=5),
            "/timelines/{form}/name",
            '"name" should be text or null, not a number',
        ),
        (
            lambda c: timeline(c, "form").update(kind="Lyrics", metadata=[]),
            "/timelines/{form}/metadata",
            '"metadata" should be an object or null, not a list',
        ),
        (
            lambda c: timeline(c, "form").update(kind="Lyrics", metadata={"a": 1}),
            "/timelines/{form}/metadata/a",
            '"a" should be text or a list, not a number',
        ),
        (
            lambda c: c["media"].update(length="12.5"),
            "/media/length",
            '"length" should be a number or null, not text',
        ),
        (
            lambda c: c.update(app_name=None),
            "/app_name",
            '"app_name" should be text, not null',
        ),
        (
            lambda c: c["scores"][0].update(content=["<mei/>", 28]),
            "/scores/0/content/1",
            'an item of "content" should be text, not a number',
        ),
        (
            lambda c: c["scores"][0].pop("source"),
            "/scores/0/source",
            '"source" is missing',
        ),
        (
            lambda c: c["scores"][0].update(source=None),
            "/scores/0/source",
            '"source" should be an object, not null',
        ),
        (
            lambda c: c["scores"][0]["source"].update(file=["a.mei"]),
            "/scores/0/source/file",
            '"file" should be text or null, not a list',
        ),
        (
            lambda c: c["scores"][0].update(
                format="svg-osmd-legacy", source=None, content=["<svg/>"]
            ),
            "/scores/0/beat_x",
            '"beat_x" is missing',
        ),
        (
            lambda c: c["scores"][0].update(
                format="svg-osmd-legacy", content=["<svg/>"], beat_x=[[0, "10"]]
            ),
            "/scores/0/beat_x/0/1",
            'an item of "beat_x" should be a number, not text',
        ),
        (
            # A component of a kind its timeline doesn't hold is kept, but its
            # structure is checked as its kind's, as the schema checks it.
            lambda c: timeline(c, "cadences")["components"].update(
                {IDS["nothing"]: {"kind": "RANGE", "end": 2.0, "start": 1.0}}
            ),
            "/timelines/{cadences}/components/{nothing}/row_id",
            '"row_id" is missing',
        ),
    ],
)
def test_a_broken_structure_is_refused_with_its_place(change, where, message):
    error = refusal(edited(change))
    assert (error.message, error.place) == (place(message), place(where))
    assert error.line is not None


def _unknown_without_name_or_metadata(timeline):
    timeline.update(kind="Lyrics")
    del timeline["name"], timeline["metadata"]


@pytest.mark.parametrize(
    "change",
    [
        # What the core reads, though the schema says more: rules for a valid
        # component, not structure.
        lambda c: component(c, "section", of="form").update(level=0),
        lambda c: timeline(c, "form").update(ordinal=0, height=-1),
        lambda c: c.update(time_unit="minutes", app_name="Other"),
        lambda c: c["media"].update(length=0),
        lambda c: c["media"].update(length=-1.5),
        lambda c: c["scores"][0].update(license=""),
        lambda c: timeline(c, "beats").update(measure_source="sung"),
        lambda c: timeline(c, "beats")["components"][IDS["beat_1"]].update(
            measure={"source": "sung"}, beat_unit={"denominator": 0, "units": "1"}
        ),
        lambda c: c["scores"][0].update(
            format="svg-osmd-legacy", content=["<svg/>"], beat_x=[[0, 1, 2], [1]]
        ),
        # Kinds and formats the core doesn't know are kept as they are.
        lambda c: c["scores"][0].update(format="musicxml", source=None),
        lambda c: component(c, "section", of="form").update(kind="SECTION", level="1"),
        lambda c: timeline(c, "form").update(kind="Lyrics", height="tall"),
        lambda c: timeline(c, "form").update(kind="HIERARCHY", height="tall"),
        # A timeline of an unknown kind needs no name or metadata.
        lambda c: _unknown_without_name_or_metadata(timeline(c, "form")),
        # A null where the schema allows one.
        lambda c: component(c, "melody_1", of="texture").update(joined_right=None),
        lambda c: timeline(c, "cadences").update(measure_table=None),
        lambda c: timeline(c, "score_timeline").update(score=None),
    ],
)
def test_what_isnt_structure_is_read(change):
    tla.loads(edited(change))


def test_a_timeline_kind_in_another_letter_case_is_a_kind_the_core_doesnt_know():
    # In a file of the current format, kinds are read as the writer writes
    # them. Only an old file's are read in any letter case: the migration
    # writes them back in the format's spelling.
    data = edited(lambda c: timeline(c, "form").update(kind="HIERARCHY", height="60"))
    form = named(tla.loads(data), "Form")
    assert form.kind == tla.UnknownKind("HIERARCHY")
    assert form.raw["height"] == "60"
    assert tla.canonical_bytes(tla.loads(data)) == data


# An integer written with a fraction of zero


def _beat_1(content):
    return timeline(content, "beats")["components"][IDS["beat_1"]]


def _beat_1_attrs(doc):
    return named(doc, "Beats").components[IDS["beat_1"]].attrs


@pytest.mark.parametrize(
    "change, get",
    [
        (
            lambda c, n: timeline(c, "form").update(ordinal=n(2)),
            lambda doc: [named(doc, "Form").ordinal],
        ),
        (
            lambda c, n: timeline(c, "form").update(kind="Lyrics", ordinal=n(2)),
            lambda doc: [named(doc, "Form").ordinal],
        ),
        (
            lambda c, n: component(c, "section", of="form").update(level=n(1)),
            lambda doc: [_section(doc).attrs["level"]],
        ),
        (
            lambda c, n: _beat_1(c).update(
                measure={"number": n(4)}, beat_unit={"denominator": n(8), "units": "1"}
            ),
            lambda doc: [
                _beat_1_attrs(doc)["measure"]["number"],
                _beat_1_attrs(doc)["beat_unit"]["denominator"],
            ],
        ),
        (
            lambda c, n: (
                timeline(c, "texture").update(default_row_height=n(30)),
                timeline(c, "texture")["rows"][0].update(height=n(-0.0)),
            ),
            lambda doc: [
                named(doc, "Texture").attrs["default_row_height"],
                named(doc, "Texture").attrs["rows"][0]["height"],
            ],
        ),
    ],
)
def test_an_integer_written_as_1_0_is_read_as_the_integer_1(change, get):
    # As JSON Schema counts it; the writer then writes 1.
    data = edited(lambda content: change(content, float))
    doc = tla.loads(data)
    assert all(type(value) is int for value in get(doc)), get(doc)
    with_integers = tla.loads(edited(lambda content: change(content, int)))
    assert tla.canonical_bytes(doc) == tla.canonical_bytes(with_integers)


def test_the_writer_writes_an_integer_given_as_1_0_as_1():
    # As the reader reads it back (FR-051a), so that the file's fingerprint
    # is that of the bytes written.
    doc = base_document()
    _section(doc).attrs["level"] = 2.0
    data = writer.checked_bytes(doc)
    assert b'"level": 2,' in data
    assert b'"level": 2.0' not in data
    assert _section(tla.loads(data)).attrs["level"] == 2


def test_the_first_problem_in_the_file_is_reported():
    def change(content):
        component(content, "cadence", of="cadences")["time"] = "1.0"
        component(content, "melody_1", of="texture")["start"] = "0.0"

    assert refusal(edited(change)).place == place(COMPONENT + "/time")


def test_a_reference_is_compared_in_nfc():
    # The reader composes both, so they name the same row.
    decomposed, composed = "Me\u0301lodie", "M\u00e9lodie"

    def change(content):
        timeline(content, "texture")["rows"][0]["id"] = composed
        for name in ("melody_1", "melody_2"):
            component(content, name, of="texture")["row_id"] = decomposed

    doc = tla.loads(edited(change))
    assert named(doc, "Texture").attrs["rows"][0]["id"] == composed


def test_a_component_of_a_timeline_of_an_unknown_kind_isnt_checked():
    # The core doesn't know what such a timeline holds: it is kept as it is.
    def change(content):
        lyrics = timeline(content, "form")
        lyrics["kind"] = "Lyrics"
        lyrics["components"] = {"1": {"text": 5}, IDS["cadence"]: {}}

    doc = tla.loads(edited(change))
    assert named(doc, "Form").raw["components"]["1"] == {"text": 5}


def test_row_ids_are_compared_in_nfc():
    # The reader composes both, so the two rows would have one id.
    decomposed, composed = "Me\u0301lodie", "M\u00e9lodie"

    def change(content):
        rows = timeline(content, "texture")["rows"]
        rows[0]["id"] = composed
        rows.append({"id": decomposed, "name": "Bass"})
        # Its ranges name a row it has, so that only the rows are refused.
        for name in ("melody_1", "melody_2"):
            component(content, name, of="texture")["row_id"] = composed

    error = refusal(edited(change))
    assert error.place == place("/timelines/{texture}/rows/1/id")
    assert error.message == f'two rows have the id "{decomposed}"'


def test_two_range_timelines_may_have_rows_with_the_same_id():
    # A row's id is unique in its timeline only.
    def change(content):
        content["timelines"][IDS["nothing"]] = {
            "kind": "Range",
            "name": "Accompaniment",
            "ordinal": 6,
            "height": 60,
            "rows": copy.deepcopy(timeline(content, "texture")["rows"]),
            "components": {},
        }

    doc = tla.loads(edited(change))
    rows = [named(doc, name).attrs["rows"] for name in ("Texture", "Accompaniment")]
    assert rows[0][0]["id"] == rows[1][0]["id"] == "aZ3k9P"


# A null is a missing key: refused only where the key is required


def _refused_nulls():
    """The keys of make_broken.base() a null is refused on: those the schema
    requires, and a metadata field's value, which is text or a list."""
    timelines = ("beats", "form", "cadences", "texture", "score_timeline")
    keys = {"/app_name", "/document_id", "/time_unit", "/media", "/media/path"}
    keys |= {"/metadata", "/metadata/title", "/timelines", "/scores"}
    keys |= {"/timelines/{form}/metadata/vocabulary"}
    for name in timelines:
        keys |= {f"/timelines/{{{name}}}/{key}" for key in ("kind", "ordinal")}
        keys |= {f"/timelines/{{{name}}}/{key}" for key in ("height", "components")}
    keys |= {"/timelines/{texture}/rows"}
    keys |= {f"/timelines/{{texture}}/rows/0/{key}" for key in ("id", "name")}
    components = {
        # A beat without a time is kept, with a warning
        # (TimeLineAnnotator/project-management#285); a null mark on the
        # first beat is refused, at the beat (FIRST_BEAT_MARK).
        ("beats", "beat_1"): (
            "kind",
            "measure",
            "beat_unit/denominator",
            "beat_unit/units",
        ),
        ("beats", "beat_2"): ("kind",),
        ("form", "section"): ("kind", "start", "end", "level"),
        ("cadences", "cadence"): ("kind", "time"),
        ("texture", "melody_1"): ("kind", "start", "end", "row_id"),
        ("texture", "melody_2"): ("kind", "start", "end", "row_id"),
    }
    for (of, name), required in components.items():
        at = f"/timelines/{{{of}}}/components/{{{name}}}"
        keys |= {f"{at}/{key}" for key in required}
    keys |= {f"/scores/0/{key}" for key in ("id", "format", "content", "source")}
    return {place(key) for key in keys}


def _members(value, path=()):
    """The path to every key of every object in `value`, but the ids that key
    timelines and components: entries, not keys."""
    if isinstance(value, dict):
        entries = path and path[-1] in ("timelines", "components")
        for key, item in value.items():
            if not entries:
                yield (*path, key)
            yield from _members(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _members(item, (*path, index))


def test_a_null_is_refused_only_where_the_key_is_required():
    refused = _refused_nulls()
    base = make_broken.base()
    found = set()
    for path in _members(base):
        if path == ("version",):
            continue  # another version is read otherwise: by the migration
        content = copy.deepcopy(base)
        parent = content
        for step in path[:-1]:
            parent = parent[step]
        parent[path[-1]] = None
        where = pointer([str(step) for step in path])
        try:
            doc = tla.loads(make_broken.text_of(content).encode("utf-8"))
        except tla.UnreadableFile as error:
            assert error.place == REFUSED_AT.get(where, where), (where, error.message)
            found.add(where)
            continue
        assert where not in refused, where
        again = tla.loads(writer.checked_bytes(doc))
        assert tla.canonical_bytes(again) == tla.canonical_bytes(doc)
        if where in NULL_IS_A_VALUE:
            continue
        # Read as if the key weren't there: its default, or nothing.
        del parent[path[-1]]
        missing = tla.loads(make_broken.text_of(content).encode("utf-8"))
        assert doc == missing, where
        assert tla.canonical_bytes(doc) == tla.canonical_bytes(missing), where
    assert found == refused


# Required, and null when the length is unknown.
NULL_IS_A_VALUE = {"/media/length"}
# Without its mark, the first beat starts no measure: refused at the beat.
FIRST_BEAT_MARK = place("/timelines/{beats}/components/{beat_1}/measure")
REFUSED_AT = {FIRST_BEAT_MARK: place("/timelines/{beats}/components/{beat_1}")}


def test_a_null_label_reads_as_its_default_and_is_left_out():
    doc = tla.loads(
        edited(lambda c: component(c, "section", of="form").update(label=None))
    )
    assert _section(doc).attrs["label"] == ""
    written = json.loads(tla.canonical_bytes(doc))
    assert "label" not in written["timelines"][FORM]["components"][IDS["section"]]


@pytest.mark.parametrize("kind", ["Hierarchy", "Lyrics"])
def test_a_null_name_reads_as_its_default_and_is_left_out(kind):
    # Whatever the timeline's kind: a name is "" by default.
    doc = tla.loads(edited(lambda c: timeline(c, "form").update(kind=kind, name=None)))
    assert doc.timelines[FORM].name == ""
    assert "name" not in json.loads(tla.canonical_bytes(doc))["timelines"][FORM]


def test_a_null_inside_a_mark_a_beat_unit_or_a_source_is_a_missing_key():
    def change(content):
        _beat_1(content).update(
            measure={"number": None, "force_display": None},
            beat_unit={"denominator": 4, "units": "1", "assumed": None},
        )
        content["scores"][0]["source"]["origin"] = None

    doc = tla.loads(edited(change))
    assert doc == base_document()
    assert tla.canonical_bytes(doc) == base_bytes()


def test_a_legacy_score_components_attributes_are_kept_as_they_are():
    # The schema doesn't name them, and every one is written: nulls included.
    note_id = IDS["nothing"]

    def change(content):
        timeline(content, "score_timeline")["components"][note_id] = {
            "kind": "NOTE",
            "start": 0.0,
            "end": 1.0,
            "step": 0,
            "accidental": None,
            "octave": 4,
            "staff_index": 0,
            "color": None,
            "comments": "",
            "display_accidental": None,
        }

    data = edited(change)
    doc = tla.loads(data)
    note = named(doc, "Score").components[note_id]
    assert (note.attrs["color"], note.attrs["accidental"]) == (None, None)
    assert tla.canonical_bytes(doc) == data


def test_none_for_a_key_with_a_default_is_left_out_when_written():
    # As a null in a file is a missing key.
    doc = base_document()
    _section(doc).attrs["label"] = None
    data = writer.checked_bytes(doc)
    written = json.loads(data)["timelines"][FORM]["components"][IDS["section"]]
    assert "label" not in written
    assert _section(tla.loads(data)).attrs["label"] == ""


@pytest.mark.parametrize("kind", ["Hierarchy", "Lyrics"])
def test_a_null_metadata_is_none(kind):
    # A null is a missing key, whatever the timeline's kind.
    doc = tla.loads(
        edited(lambda c: timeline(c, "form").update(kind=kind, metadata=None))
    )
    assert named(doc, "Form").metadata == {}


def test_a_beats_null_measure_is_no_mark():
    def change(content):
        timeline(content, "beats")["components"][IDS["beat_2"]]["measure"] = None

    doc = tla.loads(edited(change))
    beat_2 = named(doc, "Beats").components[IDS["beat_2"]]
    assert beat_2.attrs.get("measure") is None
    assert tla.canonical_bytes(doc) == base_bytes()
    # The first beat must have one (FR-081).
    error = refusal(edited(lambda c: _beat_1(c).update(measure=None)))
    assert error.place == place("/timelines/{beats}/components/{beat_1}")


# A beat timeline's measures, marked on its beats (FR-081)


def _beat_2(content):
    return timeline(content, "beats")["components"][IDS["beat_2"]]


def test_the_first_beat_is_the_first_in_time_whatever_the_files_order():
    # beat_1 comes first in the file, with the mark, but beat_2 comes first
    # in time, without one.
    data = edited(lambda c: _beat_1(c).update(time=2.0))
    error = refusal(data)
    assert error.message == 'the first beat of the timeline "Beats" has no measure mark'
    assert error.place == place("/timelines/{beats}/components/{beat_2}")
    lines = data.decode().split("\n")
    assert error.line == lines.index(f'        "{IDS["beat_2"]}": {{') + 1


def test_of_two_beats_at_the_same_time_the_first_is_the_first_by_id():
    # beat_1's id comes first: its mark makes it the first beat.
    doc = tla.loads(edited(lambda c: _beat_2(c).update(time=0.0)))
    assert named(doc, "Beats").measures.rows[0].beats == [IDS["beat_1"], IDS["beat_2"]]

    def marked_second(content):
        _beat_2(content).update(time=0.0, measure=_beat_1(content).pop("measure"))

    error = refusal(edited(marked_second))
    assert error.place == place(BEAT_1)


def test_two_beats_at_the_same_time_are_in_id_order_whatever_the_files_order():
    # beat_2, marked, comes first in the file; beat_1's id comes first.
    def change(content):
        beats = timeline(content, "beats")
        first = beats["components"].pop(IDS["beat_1"])
        _beat_2(content).update(time=0.0, measure=first.pop("measure"))
        beats["components"][IDS["beat_1"]] = first

    error = refusal(edited(change))
    assert error.place == place(BEAT_1)


def test_a_beat_timeline_without_beats_needs_no_mark():
    doc = tla.loads(edited(lambda c: timeline(c, "beats").update(components={})))
    assert named(doc, "Beats").measures.rows == []


def test_a_closing_tap_before_the_first_beat_isnt_the_first_beat():
    # A closing tap is a barline, not a beat of a measure
    # (TimeLineAnnotator/project-management#332).
    def change(content):
        _beat_1(content)["time"] = 0.5
        timeline(content, "beats")["components"][IDS["nothing"]] = {
            "kind": "BEAT",
            "time": 0.0,
            "closing": True,
        }

    doc = tla.loads(edited(change))
    assert named(doc, "Beats").measures.rows[0].beats == [IDS["beat_1"], IDS["beat_2"]]


def test_while_a_beat_has_no_time_its_first_isnt_known_and_the_file_reads():
    # The downbeat lost its time: the beat that is now first in time has no
    # mark, but the file is read, with a warning, so that the beat can be
    # fixed (TimeLineAnnotator/project-management#285).
    doc = tla.loads(edited(lambda c: _beat_1(c).pop("time")))
    assert [w.place for w in doc.warnings] == [place(BEAT_1)]
    # The downbeat without a time starts no row, and the beat after it has
    # no mark: the table is empty until the beat is fixed.
    assert named(doc, "Beats").measures.rows == []


@pytest.mark.parametrize(
    "names",
    [
        "nothing",  # no component of the file
        "section",  # a hierarchy's, in another timeline
        "beats",  # a timeline's
    ],
)
def test_a_next_that_names_no_beat_of_its_timeline_is_refused(names):
    def change(content):
        _beat_1(content)["measure"]["next"] = [IDS["beat_2"], IDS[names]]

    error = refusal(edited(change))
    assert error.message == (
        f'a measure is followed by "{IDS[names]}", which isn\'t a beat of its timeline'
    )
    assert error.place == place(BEAT_1 + "/measure/next/1")


def test_a_next_that_names_a_component_of_another_kind_in_its_timeline_is_refused():
    def change(content):
        components = timeline(content, "beats")["components"]
        components[IDS["nothing"]] = {"kind": "MARKER", "time": 3.0}
        _beat_1(content)["measure"]["next"] = [IDS["nothing"]]

    error = refusal(edited(change))
    assert error.place == place(BEAT_1 + "/measure/next/0")


def test_a_next_that_names_a_beat_of_its_timeline_is_read():
    data = edited(lambda c: _beat_1(c)["measure"].update(next=[IDS["beat_2"]]))
    doc = tla.loads(data)
    assert named(doc, "Beats").measures.rows[0].next == [IDS["beat_2"]]
    assert tla.canonical_bytes(doc) == data


@pytest.mark.parametrize(
    "change, where",
    [
        (lambda attrs: attrs.pop("measure"), BEAT_1),
        (
            lambda attrs: attrs["measure"].update(next=[IDS["nothing"]]),
            BEAT_1 + "/measure/next/0",
        ),
    ],
)
def test_the_writer_refuses_marks_the_reader_would_refuse(change, where):
    doc = base_document()
    change(_beat_1_attrs(doc))
    with pytest.raises(tla.UnreadableFile) as error:
        writer.checked_bytes(doc)
    assert error.value.place == place(where)
    tla.canonical_bytes(doc)  # written as it is, unchecked


# The schema states only structure


SCHEMA = layout._SCHEMA
# The keywords of structure: types, required keys, ids, and what holds what.
STRUCTURE = {
    "$schema",
    "$defs",
    "$ref",
    "title",
    "description",
    "default",
    "x-default-from",
    "type",
    "required",
    "properties",
    "additionalProperties",
    "propertyNames",
    "items",
    "prefixItems",
    "oneOf",
    "pattern",
    "allOf",
    "if",
    "then",
}
# Beyond them, two limits the reader refuses too: another version, and a
# score without lines.
ALSO = {
    ("const", "/properties/version"),
    ("minItems", "/$defs/score/properties/content"),
}


def _schemas(node, path=""):
    """Each schema in `node`, with its path, and whether it is an `if`'s,
    which names the kinds and formats its branch is for."""
    yield node, path
    for keyword, value in node.items():
        at = f"{path}/{keyword}"
        if keyword in ("properties", "$defs"):
            for name, schema in value.items():
                yield from _schemas(schema, f"{at}/{name}")
        elif keyword in ("oneOf", "allOf", "prefixItems"):
            for index, schema in enumerate(value):
                yield from _schemas(schema, f"{at}/{index}")
        elif keyword in ("items", "additionalProperties", "propertyNames", "then"):
            if isinstance(value, dict):
                yield from _schemas(value, at)


def test_the_schema_checks_only_types_required_keys_and_ids():
    # Every other limit is described, not checked: a value that breaks one
    # is read, and the core's rules warn about those they cover.
    limits = {
        (keyword, path)
        for schema, path in _schemas(SCHEMA)
        for keyword in schema
        if keyword not in STRUCTURE
    }
    assert limits == ALSO


def _definition(reference):
    return SCHEMA["$defs"][reference.rpartition("/")[2]]


def _null_allowed(schema):
    if "$ref" in schema and _null_allowed(_definition(schema["$ref"])):
        return True
    types = schema.get("type", [])
    if "null" in (types if isinstance(types, list) else [types]):
        return True
    return any(_null_allowed(choice) for choice in schema.get("oneOf", ()))


def test_every_key_the_schema_names_may_be_null_unless_required():
    # A null is a missing key. The media's length is required, and null when
    # the length is unknown.
    nullable_and_required = {"/properties/media/properties/length"}
    for schema, path in _schemas(SCHEMA):
        required = set(schema.get("required", ()))
        if "$ref" in schema:
            required |= set(_definition(schema["$ref"]).get("required", ()))
        for name, property_schema in schema.get("properties", {}).items():
            at = f"{path}/properties/{name}"
            if "/if/" in f"{at}/" or at.endswith("/if"):
                continue
            allowed = _null_allowed(property_schema)
            if name in required and at not in nullable_and_required:
                assert not allowed, at
            elif name not in required:
                assert allowed, at


JSON_VALUES = [None, True, 0, -1.5, "", "x", [], ["x"], {}, {"x": 1}]


def _places(value, path=()):
    """Every value in `value`, by the keys and indices that lead to it."""
    yield path
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _places(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _places(item, (*path, index))


def test_whatever_a_value_is_replaced_by_the_file_is_read_or_refused():
    # Never a crash and never part of a document (FR-050): each value of the
    # file in turn, replaced by each kind of JSON value.
    base = make_broken.base()
    for path in list(_places(base))[1:]:
        if path == ("version",):
            continue  # another version is read otherwise: by the migration
        for value in JSON_VALUES:
            content = copy.deepcopy(base)
            parent = content
            for step in path[:-1]:
                parent = parent[step]
            parent[path[-1]] = value
            data = make_broken.text_of(content).encode("utf-8")
            try:
                doc = tla.loads(data)
            except tla.UnreadableFile as error:
                assert error.place is not None, (path, value)
                assert error.line is not None, (path, value)
                continue
            # What reads, writes, and reads back as it was.
            again = tla.loads(writer.checked_bytes(doc))
            assert tla.canonical_bytes(again) == tla.canonical_bytes(doc)


# Writing: never a file the reader refuses (FR-034)


def _cadences(doc):
    return named(doc, "Cadences")


def _section(doc):
    form = named(doc, "Form")
    return form.components[IDS["section"]]


def _melody(doc):
    return named(doc, "Texture").components[IDS["melody_1"]]


def _component_under(key):
    def change(doc):
        cadences = _cadences(doc)
        cadence = cadences.components.pop(IDS["cadence"])
        cadence.id = key
        cadences.components[key] = cadence

    return change


def _set_attr(get, key, value):
    def change(doc):
        get(doc).attrs[key] = value

    return change


def _set_field(get, key, value):
    def change(doc):
        setattr(get(doc), key, value)

    return change


def _score(doc):
    return next(iter(doc.scores.values()))


def _without_level(doc):
    del _section(doc).attrs["level"]


def _second_row(doc):
    named(doc, "Texture").attrs["rows"].append({"id": "aZ3k9P", "name": "Bass"})


IN_MEMORY = {
    "a component without an id": (
        _component_under(""),
        "/timelines/{cadences}/components/",
    ),
    "an id that isn't a UUID": (
        _component_under("7"),
        "/timelines/{cadences}/components/7",
    ),
    "an id used in two timelines": (
        _component_under(IDS["section"]),
        "/timelines/{cadences}/components/{section}",
    ),
    "a document id that isn't a UUID": (
        _set_field(lambda doc: doc, "document_id", "piece-1"),
        "/document_id",
    ),
    "a time as text": (
        _set_attr(lambda doc: _cadences(doc).components[IDS["cadence"]], "time", "1"),
        COMPONENT + "/time",
    ),
    "a level missing": (_without_level, SECTION + "/level"),
    "a row named nowhere": (
        _set_attr(_melody, "row_id", "Qm7x2L"),
        MELODY + "/row_id",
    ),
    "two rows with one id": (_second_row, "/timelines/{texture}/rows/1/id"),
    "a range joined to nothing": (
        _set_attr(_melody, "joined_right", IDS["nothing"]),
        MELODY + "/joined_right",
    ),
    "a score named nowhere": (
        _set_attr(lambda doc: named(doc, "Score"), "score", IDS["nothing"]),
        "/timelines/{score_timeline}/score",
    ),
    "a score's measure table named nowhere": (
        _set_attr(lambda doc: named(doc, "Score"), "measure_table", IDS["nothing"]),
        "/timelines/{score_timeline}/measure_table",
    ),
    "an imported timeline's measure table named nowhere": (
        _set_attr(_cadences, "measure_table", IDS["nothing"]),
        "/timelines/{cadences}/measure_table",
    ),
    "a score without lines": (
        _set_field(_score, "lines", []),
        "/scores/0/content",
    ),
    "a score line that isn't text": (
        _set_field(_score, "lines", ["<mei/>", 28]),
        "/scores/0/content/1",
    ),
    "score content that isn't a list": (
        _set_field(_score, "lines", "<mei/>"),
        "/scores/0/content",
    ),
    "an MEI score without a source": (
        _set_field(_score, "source", None),
        "/scores/0/source",
    ),
    "the file's metadata not an object": (
        _set_field(lambda doc: doc, "metadata", ["Broken"]),
        "/metadata",
    ),
    "a timeline's metadata not an object": (
        _set_field(lambda doc: named(doc, "Form"), "metadata", "form"),
        "/timelines/{form}/metadata",
    ),
    "a component's metadata not an object": (
        _set_field(_section, "metadata", 5),
        SECTION + "/metadata",
    ),
    "a timeline kind that isn't text": (
        _set_field(lambda doc: named(doc, "Form"), "kind", tla.UnknownKind(5)),
        "/timelines/{form}/kind",
    ),
    "a component kind that isn't text": (
        _set_field(_section, "kind", tla.UnknownKind(5)),
        SECTION + "/kind",
    ),
}


# What JSON Schema can't check (FR-090): the file canonical_bytes writes for
# one of these is valid against the schema, and only the core refuses it.
CORE_ONLY = {
    "a range joined to nothing",
    "a row named nowhere",
    "a score named nowhere",
    "a score's measure table named nowhere",
    "an id used in two timelines",
    "an imported timeline's measure table named nowhere",
    "two rows with one id",
}


def _written(case):
    """A case of IN_MEMORY, for a test that writes it with canonical_bytes,
    which doesn't check: every file the tests write is checked against the
    schema, which refuses this one unless only the core can (tests/conftest.py)."""
    if case in CORE_ONLY:
        return case
    reason = "a broken document, written on purpose"
    return pytest.param(case, marks=pytest.mark.writes_outside_the_schema(reason))


def _broken(case):
    change, where = IN_MEMORY[case]
    doc = base_document()
    change(doc)
    return doc, place(where)


@pytest.fixture(params=sorted(IN_MEMORY))
def broken_document(request):
    return _broken(request.param)


@pytest.fixture(params=[_written(case) for case in sorted(IN_MEMORY)])
def written_broken_document(request):
    return _broken(request.param)


def test_the_writer_refuses_a_document_the_reader_would_refuse(
    written_broken_document,
):
    doc, where = written_broken_document
    with pytest.raises(tla.UnreadableFile) as error:
        writer.checked_bytes(doc, path="piece.tla")
    assert error.value.place == where
    assert error.value.path == Path("piece.tla")
    # The same refusal as reading what canonical_bytes writes, which
    # doesn't check: the line is that of the place in the bytes it would write.
    data = tla.canonical_bytes(doc)
    from_reader = refusal(data)
    assert (error.value.message, error.value.place, error.value.line) == (
        from_reader.message,
        from_reader.place,
        from_reader.line,
    )
    assert error.value.line == lines_of(data.decode(), [where])[where]


@pytest.mark.skipif(not hasattr(tla, "write"), reason="tla.write isn't there yet")
def test_write_refuses_a_document_the_reader_would_refuse_and_writes_nothing(
    broken_document, tmp_path
):
    doc, where = broken_document
    path = tmp_path / "piece.tla"
    with pytest.raises(tla.UnreadableFile) as error:
        tla.write(path, doc)
    assert error.value.place == where
    assert list(tmp_path.iterdir()) == []


def test_the_writer_writes_what_the_reader_reads():
    doc = base_document()
    assert writer.checked_bytes(doc) == tla.canonical_bytes(doc) == base_bytes()


def test_the_writer_takes_values_of_a_kind_of_jsons_types():
    # As json.dumps writes them: a str subclass as text, an int's as a number.
    class Label(str):
        pass

    class Level(int):
        pass

    doc = base_document()
    _section(doc).attrs.update(label=Label("A"), level=Level(1))
    assert writer.checked_bytes(doc) == base_bytes()


def test_canonical_bytes_doesnt_check(written_broken_document):
    # It is what a file would hold: write checks before writing it.
    doc, _ = written_broken_document
    tla.canonical_bytes(doc)


# Finding lines


def test_lines_of_finds_keys_items_and_the_top():
    text = '{\n  "a": [\n    1,\n    {"b~/c": 2}\n  ],\n  "": 3\n}\n'
    places = ["", "/a", "/a/0", "/a/1", "/a/1/b~0~1c", "/", "/a/1/missing", "/x"]
    assert lines_of(text, places) == {
        "": 1,
        "/a": 2,
        "/a/0": 3,
        "/a/1": 4,
        "/a/1/b~0~1c": 4,
        "/": 6,
        "/a/1/missing": 4,  # the object it is missing from
        "/x": 1,
    }


def test_lines_of_reads_escaped_keys():
    text = '{"a\\u00e9": {\n"k\\n": 1}}'
    assert lines_of(text, ["/a\u00e9/k\n"]) == {"/a\u00e9/k\n": 2}
