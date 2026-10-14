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
from tilia_core.tla import writer
from tilia_core.tla.parse import lines_of

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


COMPONENT = "/timelines/{cadences}/components/{cadence}"
SECTION = "/timelines/{form}/components/{section}"
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
    "metadata-not-an-object.tla": (
        '"metadata" should be an object, not a list',
        "/timelines/{form}/metadata",
        40,
    ),
    "score-without-lines.tla": (
        "the score's content has no lines",
        "/scores/0/content",
        111,
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
            lambda c: timeline(c, "form").update(ordinal=2.0),
            "/timelines/{form}/ordinal",
            '"ordinal" should be an integer, not a number',
        ),
        (
            lambda c: timeline(c, "form").update(is_visible=1),
            "/timelines/{form}/is_visible",
            '"is_visible" should be true or false, not a number',
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
            lambda c: component(c, "section", of="form").update(label=None),
            SECTION + "/label",
            '"label" should be text, not null',
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
                measure=None
            ),
            "/timelines/{beats}/components/{beat_1}/measure",
            '"measure" should be an object, not null',
        ),
        (
            lambda c: timeline(c, "beats")["components"][IDS["beat_1"]].update(
                measure={"number": "1"}
            ),
            "/timelines/{beats}/components/{beat_1}/measure/number",
            '"number" should be an integer, not text',
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
            lambda c: c["scores"][0].update(license=None),
            "/scores/0/license",
            '"license" should be text, not null',
        ),
        (
            lambda c: c["scores"][0]["source"].update(file=["a.mei"]),
            "/scores/0/source/file",
            '"file" should be text, not a list',
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
    ],
)
def test_a_broken_structure_is_refused_with_its_place(change, where, message):
    error = refusal(edited(change))
    assert (error.message, error.place) == (place(message), place(where))
    assert error.line is not None


@pytest.mark.parametrize(
    "change",
    [
        # What the core reads, though the schema says more: rules for a valid
        # component, not structure.
        lambda c: component(c, "section", of="form").update(level=0),
        lambda c: timeline(c, "form").update(ordinal=0),
        lambda c: c.update(time_unit="minutes", app_name="Other"),
        lambda c: c["media"].update(length=0),
        lambda c: c["scores"][0].update(license=""),
        # Kinds and formats the core doesn't know are kept as they are.
        lambda c: c["scores"][0].update(format="musicxml", source=None),
        lambda c: component(c, "section", of="form").update(kind="SECTION", level="1"),
        lambda c: timeline(c, "form").update(kind="Lyrics", height="tall"),
        # A null where the schema allows one.
        lambda c: component(c, "melody_1", of="texture").update(joined_right=None),
        lambda c: timeline(c, "cadences").update(measure_table=None),
        lambda c: timeline(c, "score_timeline").update(score=None),
    ],
)
def test_what_isnt_structure_is_read(change):
    tla.loads(edited(change))


def test_a_timeline_kind_is_checked_as_the_reader_reads_it():
    # In any letter case, as TiLiA 0.7 reads it, so that writing it back as
    # "Hierarchy" doesn't make a file the reader refuses.
    error = refusal(
        edited(lambda c: timeline(c, "form").update(kind="HIERARCHY", height="60"))
    )
    assert error.place == place("/timelines/{form}/height")


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
    "a label that is None": (
        _set_attr(_section, "label", None),
        SECTION + "/label",
    ),
    "a level missing": (_without_level, SECTION + "/level"),
    "a row named nowhere": (
        _set_attr(_melody, "row_id", "Qm7x2L"),
        MELODY + "/row_id",
    ),
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


@pytest.fixture(params=sorted(IN_MEMORY))
def broken_document(request):
    change, where = IN_MEMORY[request.param]
    doc = base_document()
    change(doc)
    return doc, place(where)


def test_the_writer_refuses_a_document_the_reader_would_refuse(broken_document):
    doc, where = broken_document
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


def test_canonical_bytes_doesnt_check(broken_document):
    # It is what a file would hold: write checks before writing it.
    doc, _ = broken_document
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
