"""Old score timelines through the migration (FR-022, contracts/migration.md,
*Scores*): the SVG TiLiA 0.x stored in a score timeline, with its viewer's
beat positions, becomes a legacy score in the file's `scores`, which the
timeline names; the timeline's components stay with it, with new ids."""

import copy
import json
import unicodedata
from pathlib import Path

import pytest

from tilia_core import tla
from tilia_core.tla.ids import derived_document_id, migrated_id

HERE = Path(__file__).parent
OLD = HERE / "old"
SVG = (HERE / "scores" / "osmd-legacy.svg").read_bytes().decode("utf-8")
# The old files with a score timeline: each holds SVG, as its svg_data.
WITH_A_SCORE = ["0.5.15.tla", "0.5.15-saved-by-0.7.0.tla", "0.7.0.tla"]
OLD_BEAT_X = {"0.0": 12.5, "0.5": 48.0}
BEAT_X = [[0.0, 12.5], [0.5, 48.0]]
SCORE_TIMELINE = ("timelines", "7")


def content_of(path):
    return json.loads(path.read_bytes())


def loads(content):
    return tla.loads(json.dumps(content).encode())


def old_score_timeline(content):
    """The old file's score timeline: its old id, position and content."""
    return next(
        (key, position, timeline)
        for position, (key, timeline) in enumerate(content["timelines"].items())
        if timeline["kind"].lower().removesuffix("_timeline") == "score"
    )


def new_ids(doc, old_id, position):
    """The ids the migration gives a score timeline and its score."""
    return (
        migrated_id(doc.document_id, "timeline", old_id, position=position),
        migrated_id(doc.document_id, "score", old_id, position=position),
    )


# The old files with a score timeline


@pytest.fixture(params=WITH_A_SCORE)
def old_file(request):
    return OLD / request.param


def test_an_old_score_timelines_svg_becomes_a_legacy_score(old_file):
    doc = tla.read(old_file)
    old_id, position, old = old_score_timeline(content_of(old_file))
    assert old["svg_data"] == SVG
    _, score_id = new_ids(doc, old_id, position)
    (score,) = doc.scores.values()
    assert score.id == score_id
    assert score.format == "svg-osmd-legacy"
    assert score.text == SVG
    assert (score.source, score.license) == (None, None)
    assert score.extra == {"beat_x": BEAT_X}
    (written,) = json.loads(tla.canonical_bytes(doc))["scores"]
    assert written == {
        "id": score_id,
        "format": "svg-osmd-legacy",
        "content": [SVG],
        "beat_x": BEAT_X,
    }


def test_the_timeline_names_its_score_and_has_no_measure_table(old_file):
    doc = tla.read(old_file)
    old_id, position, _ = old_score_timeline(content_of(old_file))
    timeline_id, score_id = new_ids(doc, old_id, position)
    timeline = doc.timelines[timeline_id]
    assert timeline.attrs["score"] == score_id
    assert timeline.attrs["measure_table"] is None
    assert timeline.extra == {}
    written = json.loads(tla.canonical_bytes(doc))["timelines"][timeline_id]
    assert written["score"] == score_id
    assert not {"measure_table", "svg_data", "viewer_beat_x"} & set(written)


def test_the_timelines_components_stay_with_new_ids(old_file):
    doc = tla.read(old_file)
    old_id, position, old = old_score_timeline(content_of(old_file))
    timeline_id, _ = new_ids(doc, old_id, position)
    components = doc.timelines[timeline_id].components
    expected = {}
    for index, (key, component) in enumerate(old["components"].items()):
        new_id = migrated_id(doc.document_id, "component", old_id, key, position=index)
        attrs = {k: v for k, v in component.items() if k not in ("kind", "hash")}
        if component["kind"] == "CLEF":
            # As TiLiA 0.7 reads a clef's icon.
            attrs["icon"] = attrs["icon"].removesuffix(".svg")
        expected[new_id] = (component["kind"].lower(), attrs)
    assert {key: (c.kind, c.attrs) for key, c in components.items()} == expected
    assert all(not c.extra and not c.metadata for c in components.values())


def test_annotations_keep_their_place_on_the_svg():
    doc = tla.read(OLD / "0.7.0.tla")
    (annotation,) = (
        component
        for timeline in doc.timelines.values()
        for component in timeline.components.values()
        if component.kind == "score_annotation"
    )
    assert annotation.attrs == {
        "x": 10.5,
        "y": 20.0,
        "viewer_id": 0,
        "text": "Allegro",
        "font_size": 12,
    }


# The migration, on small files


def old_file_content(**score_timeline):
    """A file of TiLiA 0.7 with a score timeline (old id 7), its SVG and beat
    positions, a note and an annotation; `score_timeline` changes it."""
    timeline = {
        "kind": "Score",
        "height": 1,
        "is_visible": True,
        "name": "Score",
        "ordinal": 2,
        "svg_data": SVG,
        "viewer_beat_x": dict(OLD_BEAT_X),
        "hash": "5a6b",
        "components_hash": "7c8d",
        "components": {
            "8": {
                "start": 0.0,
                "end": 0.5,
                "step": 5,
                "accidental": 0,
                "octave": 4,
                "staff_index": 0,
                "color": None,
                "comments": "",
                "display_accidental": False,
                "kind": "NOTE",
                "hash": "9e0f",
            },
            "9": {
                "x": 10.5,
                "y": 20.0,
                "viewer_id": 0,
                "text": "Allegro",
                "font_size": 12,
                "kind": "SCORE_ANNOTATION",
                "hash": "1a2b",
            },
        },
    }
    timeline.update(score_timeline)
    return {
        "file_path": "C:/Users/someone/corpus/piece.tla",
        "media_path": "",
        "media_metadata": {"title": "Piece", "notes": "", "composer": ""},
        "timelines": {
            "1": {
                "kind": "Slider",
                "height": 40,
                "is_visible": True,
                "name": "",
                "ordinal": 1,
                "hash": "0a1b",
                "components_hash": "2c3d",
                "components": {},
            },
            "7": timeline,
        },
        "timelines_hash": "3e4f",
        "app_name": "TiLiA",
        "version": "0.7.0",
    }


def score_of(doc):
    (score,) = doc.scores.values()
    return score


def score_timeline_of(doc):
    return next(tl for tl in doc.timelines.values() if tl.kind == "score")


def test_beat_x_is_in_time_order_by_value():
    # In text order, "10.0" would come before "2.0".
    beat_x = {"10.0": 300.5, "2.0": 120, "0.5": 48.0, "1.3333333333333333": 100.25}
    doc = loads(old_file_content(viewer_beat_x=beat_x))
    assert score_of(doc).extra["beat_x"] == [
        [0.5, 48.0],
        [1.3333333333333333, 100.25],
        [2.0, 120],
        [10.0, 300.5],
    ]


@pytest.mark.parametrize("beat_x", [None, {}, "missing"])
def test_a_score_without_beat_positions_has_an_empty_beat_x(beat_x):
    # TiLiA's default, {}, until its viewer draws the score.
    content = old_file_content(viewer_beat_x=beat_x)
    if beat_x == "missing":
        del content["timelines"]["7"]["viewer_beat_x"]
    doc = loads(content)
    assert score_of(doc).extra == {"beat_x": []}
    assert score_timeline_of(doc).extra == {}


def test_the_svg_is_stored_as_its_lines_without_nfc():
    svg = '<svg>\r\n<text>"Sta\u0308ndchen" \\ \t</text>\r\n</svg>\r\n'
    doc = loads(old_file_content(svg_data=svg))
    assert score_of(doc).lines == [
        "<svg>",
        '<text>"Sta\u0308ndchen" \\ \t</text>',
        "</svg>",
        "",
    ]
    data = tla.canonical_bytes(doc)
    assert "Sta\u0308ndchen".encode() in data
    assert unicodedata.normalize("NFC", "Sta\u0308ndchen").encode() not in data


@pytest.mark.parametrize("svg", ["", None, "missing"])
def test_a_score_timeline_without_svg_gets_no_score_and_no_score_key(svg):
    # No score imported yet: TiLiA's default svg_data, "", and viewer_beat_x, {}.
    content = old_file_content(svg_data=svg, viewer_beat_x={})
    if svg == "missing":
        del content["timelines"]["7"]["svg_data"]
    doc = loads(content)
    assert doc.scores == {}
    timeline = score_timeline_of(doc)
    assert timeline.attrs["score"] is None
    assert timeline.extra == {}
    assert len(timeline.components) == 2
    written = json.loads(tla.canonical_bytes(doc))
    assert written["scores"] == []
    (written_timeline,) = (
        tl for tl in written["timelines"].values() if tl["kind"] == "Score"
    )
    assert not {"score", "svg_data", "viewer_beat_x"} & set(written_timeline)


def test_each_score_timeline_names_its_own_score():
    content = old_file_content()
    second = copy.deepcopy(content["timelines"]["7"])
    second.update(name="Second", ordinal=3, svg_data=SVG.replace("svg>", "svg> "))
    content["timelines"]["12"] = second
    doc = loads(content)
    first_id, first_score = new_ids(doc, "7", 1)
    second_id, second_score = new_ids(doc, "12", 2)
    assert list(doc.scores) == sorted([first_score, second_score])
    assert doc.timelines[first_id].attrs["score"] == first_score
    assert doc.timelines[second_id].attrs["score"] == second_score
    assert doc.scores[second_score].text == SVG.replace("svg>", "svg> ")


def test_a_score_whose_timelines_old_id_isnt_an_integer_takes_its_position():
    content = old_file_content()
    content["timelines"] = {
        "1": content["timelines"]["1"],
        "score": content["timelines"]["7"],
    }
    doc = loads(content)
    _, score_id = new_ids(doc, "score", 1)
    assert list(doc.scores) == [score_id]
    assert score_timeline_of(doc).attrs["score"] == score_id


def test_the_migration_warns_about_nothing_in_a_score_timeline():
    assert loads(old_file_content()).warnings == []


# The document id


def test_the_document_id_is_derived_with_the_score_under_its_timelines_old_id():
    # Before the new ids replace the old ones: the score's is its timeline's.
    expected = derived_document_id(
        {
            "time_unit": "seconds",
            "media": {"path": ""},
            "metadata": {"title": "Piece", "notes": "", "composer": ""},
            "timelines": {
                "1": {"kind": "Slider", "ordinal": 1, "height": 40, "components": {}},
                "7": {
                    "kind": "Score",
                    "name": "Score",
                    "ordinal": 2,
                    "height": 1,
                    "score": "7",
                    "components": {
                        "8": {
                            "kind": "NOTE",
                            "start": 0.0,
                            "end": 0.5,
                            "step": 5,
                            "accidental": 0,
                            "octave": 4,
                            "staff_index": 0,
                            "color": None,
                            "comments": "",
                            "display_accidental": False,
                        },
                        "9": {
                            "kind": "SCORE_ANNOTATION",
                            "x": 10.5,
                            "y": 20.0,
                            "viewer_id": 0,
                            "text": "Allegro",
                            "font_size": 12,
                        },
                    },
                },
            },
            "scores": [
                {
                    "id": "7",
                    "format": "svg-osmd-legacy",
                    "content": [SVG],
                    "beat_x": BEAT_X,
                }
            ],
        }
    )
    assert loads(old_file_content()).document_id == expected


@pytest.mark.parametrize(
    "change",
    [
        {"svg_data": SVG.replace("svg>", "svg> ")},
        {"viewer_beat_x": {"0.0": 12.5, "0.5": 48.5}},
        {"svg_data": ""},
    ],
    ids=["svg", "a beat position", "no svg"],
)
def test_the_document_id_changes_with_the_svg_and_its_beat_positions(change):
    assert (
        loads(old_file_content(**change)).document_id
        != loads(old_file_content()).document_id
    )


def test_the_document_id_ignores_the_order_of_the_scores_timelines():
    content = old_file_content()
    second = copy.deepcopy(content["timelines"]["7"])
    second.update(name="Second", ordinal=3, svg_data=SVG.replace("svg>", "svg> "))
    content["timelines"]["12"] = second
    reordered = copy.deepcopy(content)
    reordered["timelines"] = dict(reversed(list(content["timelines"].items())))
    assert loads(reordered).document_id == loads(content).document_id


# Shapes TiLiA never writes, from files edited by hand: refused, naming the
# place in the old file (TimeLineAnnotator/project-management#359, pending).


@pytest.mark.parametrize("svg", [7, ["<svg/>"], {"svg": "<svg/>"}, True])
def test_svg_data_that_isnt_text_is_refused(svg):
    with pytest.raises(tla.UnreadableFile) as error:
        loads(old_file_content(svg_data=svg))
    assert (error.value.place, error.value.message) == (
        "/timelines/7/svg_data",
        "expected text at /timelines/7/svg_data",
    )


@pytest.mark.parametrize("beat_x", [[[0.0, 12.5]], "0.0: 12.5", 1, True])
def test_beat_positions_that_arent_an_object_are_refused(beat_x):
    with pytest.raises(tla.UnreadableFile) as error:
        loads(old_file_content(viewer_beat_x=beat_x))
    assert (error.value.place, error.value.message) == (
        "/timelines/7/viewer_beat_x",
        "expected an object at /timelines/7/viewer_beat_x",
    )


@pytest.mark.parametrize(
    "key, place",
    [
        ("abc", "abc"),
        ("NaN", "NaN"),
        ("Infinity", "Infinity"),
        ("1e999", "1e999"),
        (" 1.0", " 1.0"),
        ("1_0", "1_0"),
        ("", ""),
        ("1/2", "1~12"),
        ("\u0661.0", "\u0661.0"),  # an Arabic-Indic digit, which float() reads
    ],
)
def test_a_beat_position_whose_time_isnt_a_number_is_refused(key, place):
    with pytest.raises(tla.UnreadableFile) as error:
        loads(old_file_content(viewer_beat_x={"0.0": 12.5, key: 48.0}))
    assert error.value.place == f"/timelines/7/viewer_beat_x/{place}"
    assert error.value.message == (
        f"{json.dumps(key, ensure_ascii=False)} in viewer_beat_x isn't a number"
    )


@pytest.mark.parametrize("key", ["-0.5", "1e-05", "1E+16", "2", "0.30000000000000004"])
def test_beat_positions_times_are_numbers_as_json_writes_them(key):
    doc = loads(old_file_content(viewer_beat_x={key: 7.0}))
    assert score_of(doc).extra["beat_x"] == [[float(key), 7.0]]


@pytest.mark.parametrize("x", ["12.5", None, True, [12.5], {}])
def test_a_beat_position_that_isnt_a_number_is_refused(x):
    with pytest.raises(tla.UnreadableFile) as error:
        loads(old_file_content(viewer_beat_x={"0.0": 12.5, "0.5": x}))
    assert (error.value.place, error.value.message) == (
        "/timelines/7/viewer_beat_x/0.5",
        "expected a number at /timelines/7/viewer_beat_x/0.5",
    )


def test_beat_positions_without_svg_stay_on_the_timeline():
    # No score to keep them: kept as they are, as a key the core doesn't know.
    doc = loads(old_file_content(svg_data="", viewer_beat_x=dict(OLD_BEAT_X)))
    assert doc.scores == {}
    timeline = score_timeline_of(doc)
    assert timeline.extra == {"viewer_beat_x": OLD_BEAT_X}
    assert timeline.attrs["score"] is None
    again = tla.loads(tla.canonical_bytes(doc))
    assert score_timeline_of(again).extra == {"viewer_beat_x": OLD_BEAT_X}


@pytest.mark.parametrize("svg", [SVG, ""], ids=["with svg", "without"])
def test_a_score_key_in_an_old_score_timeline_is_refused(svg):
    # A key of the current format: the migration couldn't keep its value.
    with pytest.raises(tla.UnreadableFile) as error:
        loads(old_file_content(svg_data=svg, score="another"))
    assert (error.value.place, error.value.message) == (
        "/timelines/7/score",
        'a file from TiLiA 0.7.0 can\'t hold "score", a key of the current format',
    )


def test_a_null_score_key_in_an_old_score_timeline_is_a_missing_one():
    doc = loads(old_file_content(score=None))
    assert score_timeline_of(doc).attrs["score"] == score_of(doc).id
    assert doc.document_id == loads(old_file_content()).document_id
