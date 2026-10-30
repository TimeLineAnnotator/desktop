"""Scores inside a `.tla` file (FR-130–FR-135, SC-012): the file's `scores`
list, empty for a file without a score; each score's content stored as its
lines, which join to give the score back, with CRLF turned into LF and its
text never in NFC; and score timelines naming their score and their measure
table by id.

The scores are real files, in `scores/`: an MEI written by Verovio from a
short MusicXML of our own, and the SVG of an old file's score timeline."""

import json
import unicodedata
from pathlib import Path

import pytest

from tilia_core import tla

HERE = Path(__file__).parent
MEI = HERE / "scores" / "serenade.mei"
SVG = HERE / "scores" / "osmd-legacy.svg"
EVERY_KIND = HERE / "golden" / "every-kind.tla"
# The old file whose score timeline's SVG is `SVG`.
OLD_WITH_SVG = HERE / "old" / "0.7.0.tla"

SOURCE = {
    "file": "serenade.musicxml",
    "origin": "made for these tests",
    "converter": "Verovio 6.3.0",
}
BEAT_X = [[0.0, 12.5], [0.5, 48.0]]
DECOMPOSED = unicodedata.normalize("NFD", "Ständchen")


def text_of(path):
    return path.read_bytes().decode("utf-8")


def mei_score(text, **fields):
    score = tla.Score(id=tla.new_id(), format="mei", source=dict(SOURCE), **fields)
    score.text = text
    return score


def legacy_score(text):
    score = tla.Score(
        id=tla.new_id(), format="svg-osmd-legacy", extra={"beat_x": BEAT_X}
    )
    score.text = text
    return score


def with_scores(*scores):
    doc = tla.new_document()
    doc.scores = {score.id: score for score in scores}
    return doc


def written_and_read(doc, tmp_path):
    """The file's bytes once `doc` is written, and the document read from it."""
    path = tmp_path / "piece.tla"
    tla.write(path, doc)
    return path.read_bytes(), tla.read(path)


# The score files


def test_the_mei_holds_what_a_scores_content_must_keep():
    text = text_of(MEI)
    for kept in ('"', "\\", "\t", "Σερενάτα", "セレナーデ", "Dvořák", DECOMPOSED):
        assert kept in text
    assert not unicodedata.is_normalized("NFC", text)
    assert "<name" in text and ">Verovio</name>" in text
    assert "\r" not in text
    assert text.endswith("</mei>\n")


def test_the_svg_is_an_old_files_svg_data():
    old = json.loads(OLD_WITH_SVG.read_bytes())
    (score_timeline,) = (
        tl for tl in old["timelines"].values() if tl["kind"] == "Score"
    )
    assert text_of(SVG) == score_timeline["svg_data"]


def forms(text):
    """The score as a file may hold it: with LF or CRLF line endings, each
    with and without a final newline."""
    body = text.replace("\r\n", "\n").rstrip("\n")
    return {
        "LF": body + "\n",
        "LF, no final newline": body,
        "CRLF": body.replace("\n", "\r\n") + "\r\n",
        "CRLF, no final newline": body.replace("\n", "\r\n"),
    }


FORMS = list(forms(""))


# A score's content comes back as it was imported


@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize(
    "path, make", [(MEI, mei_score), (SVG, legacy_score)], ids=["MEI", "SVG"]
)
def test_a_scores_lines_join_to_give_the_score_back_with_lf(tmp_path, path, make, form):
    text = forms(text_of(path))[form]
    score = make(text)
    _, doc = written_and_read(with_scores(score), tmp_path)
    expected = text.replace("\r\n", "\n")
    lines = doc.scores[score.id].lines
    assert doc.scores[score.id].text == expected
    assert lines == expected.split("\n")
    # A final newline is a final empty line.
    assert (lines[-1] == "") == text.endswith("\n")
    assert not any(line.endswith("\r") for line in lines)


@pytest.mark.parametrize("form", FORMS)
def test_a_score_is_kept_out_of_nfc_in_the_file_and_in_the_document(tmp_path, form):
    text = forms(text_of(MEI))[form]
    data, doc = written_and_read(with_scores(mei_score(text)), tmp_path)
    (score,) = doc.scores.values()
    assert DECOMPOSED in score.text
    assert not unicodedata.is_normalized("NFC", score.text)
    assert DECOMPOSED.encode() in data
    assert unicodedata.normalize("NFC", DECOMPOSED).encode() not in data


def test_a_score_is_escaped_only_as_json_requires(tmp_path):
    data, _ = written_and_read(with_scores(mei_score(text_of(MEI))), tmp_path)
    # Characters as they are, quotes, backslashes and tabs escaped.
    for text in ("Σερενάτα", "セレナーデ", "Dvořák"):
        assert text.encode() in data
    assert b'<title>Sta\xcc\x88ndchen (\\"klein\\")' in data
    assert b"a tempo\\t\\\\ dolce" in data
    assert b"\\u" not in data


@pytest.mark.parametrize("form", FORMS)
def test_reading_and_writing_a_score_again_changes_nothing(tmp_path, form):
    text = forms(text_of(MEI))[form]
    data, doc = written_and_read(with_scores(mei_score(text)), tmp_path)
    assert tla.canonical_bytes(doc) == data
    (score,) = doc.scores.values()
    score.text = score.text  # the text it has: the same lines
    assert tla.canonical_bytes(doc) == data


def test_a_lone_cr_stays_in_its_line_and_crs_before_an_lf_go(tmp_path):
    score = mei_score("<mei>\r\r\n<!-- a\rb -->\r\n</mei>\r")
    _, doc = written_and_read(with_scores(score), tmp_path)
    assert doc.scores[score.id].lines == ["<mei>", "<!-- a\rb -->", "</mei>\r"]


@pytest.mark.parametrize(
    "text",
    [
        "<mei><measure n='1'>",  # not well-formed
        "not XML at all",
        '<svg onload="alert(1)"><script>alert(2)</script></svg>',
        "\x00\x1f ﻿",
    ],
    ids=["cut short", "not XML", "a script", "control characters"],
)
def test_a_scores_content_is_text_kept_as_it_is_never_parsed(tmp_path, text):
    # FR-135: checking a score is WP7's, and nothing in it runs.
    score = mei_score(text)
    _, doc = written_and_read(with_scores(score), tmp_path)
    assert doc.scores[score.id].text == text


# The scores list


def test_a_file_without_a_score_has_an_empty_scores_list(tmp_path):
    data, doc = written_and_read(tla.new_document(), tmp_path)
    assert json.loads(data)["scores"] == []
    assert data.endswith(b'\n  "scores": []\n}\n')
    assert doc.scores == {}


def test_three_scores_in_one_file_each_come_back_with_all_they_hold(tmp_path):
    mei = text_of(MEI)
    stated = mei_score(mei, license="CC0-1.0")
    undetermined = mei_score(mei.replace("dolce", "dolcissimo"))
    legacy = legacy_score(text_of(SVG))
    doc = with_scores(legacy, undetermined, stated)
    data, again = written_and_read(doc, tmp_path)
    expected = {
        stated.id: ("mei", SOURCE, "CC0-1.0", mei, {}),
        undetermined.id: (
            "mei",
            SOURCE,
            "NOASSERTION",
            mei.replace("dolce", "dolcissimo"),
            {},
        ),
        legacy.id: ("svg-osmd-legacy", None, None, text_of(SVG), {"beat_x": BEAT_X}),
    }
    assert list(again.scores) == sorted(expected)
    for score_id, score in again.scores.items():
        assert score.id == score_id
        assert (
            score.format,
            score.source,
            score.license,
            score.text,
            score.extra,
        ) == expected[score_id]
    # In id order, each in its shape's order, a licence at its default left out.
    written = json.loads(data)["scores"]
    assert [score["id"] for score in written] == sorted(expected)
    keys = {
        stated.id: ["id", "format", "source", "license", "content"],
        undetermined.id: ["id", "format", "source", "content"],
        legacy.id: ["id", "format", "content", "beat_x"],
    }
    assert [list(score) for score in written] == [keys[s["id"]] for s in written]


def test_one_changed_line_of_a_score_changes_one_line_of_the_file(tmp_path):
    doc = with_scores(
        mei_score(text_of(MEI)),
        mei_score(text_of(MEI)),
        legacy_score(text_of(SVG)),
    )
    before, doc = written_and_read(doc, tmp_path)
    score = doc.scores[sorted(doc.scores)[1]]
    score.text = score.text.replace("a tempo\t\\ dolce", "a tempo\t\\ dolcissimo")
    after, _ = written_and_read(doc, tmp_path)
    old, new = before.split(b"\n"), after.split(b"\n")
    assert len(old) == len(new)
    changed = [index for index, line in enumerate(old) if line != new[index]]
    assert len(changed) == 1
    (index,) = changed
    assert b"dolcissimo" in new[index] and b"dolcissimo" not in old[index]


# An MEI score built through the API


def test_an_mei_score_without_a_source_is_refused_and_nothing_written(tmp_path):
    # The reader would refuse the file: an MEI score requires its source.
    score = tla.Score(id=tla.new_id(), format="mei")
    score.text = text_of(MEI)
    path = tmp_path / "piece.tla"
    with pytest.raises(tla.UnreadableFile) as error:
        tla.write(path, with_scores(score))
    assert (error.value.place, error.value.message) == (
        "/scores/0/source",
        '"source" is missing',
    )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.writes_outside_the_schema("an MEI score without its source")
def test_the_reader_refuses_an_mei_score_without_a_source_as_write_does():
    score = tla.Score(id=tla.new_id(), format="mei")
    score.text = text_of(MEI)
    data = tla.canonical_bytes(with_scores(score))
    with pytest.raises(tla.UnreadableFile) as error:
        tla.loads(data)
    assert error.value.place == "/scores/0/source"


def test_an_mei_score_without_a_licence_is_written_without_one(tmp_path):
    # Nobody has determined it: NOASSERTION, the default, left out.
    score = tla.Score(id=tla.new_id(), format="mei", source={"file": "x.musicxml"})
    assert score.license is None
    score.text = text_of(MEI)
    data, doc = written_and_read(with_scores(score), tmp_path)
    (written,) = json.loads(data)["scores"]
    assert "license" not in written
    assert doc.scores[score.id].license == "NOASSERTION"
    assert doc.scores[score.id].source == {"file": "x.musicxml"}


# Score timelines


def score_timeline(ordinal, **attrs):
    return tla.Timeline(
        id=tla.new_id(),
        kind="score",
        ordinal=ordinal,
        name=f"Score {ordinal}",
        attrs={"height": 160, **attrs},
    )


def test_a_score_timeline_names_its_score_and_its_measure_table():
    doc = tla.read(EVERY_KIND)
    (timeline,) = (tl for tl in doc.timelines.values() if tl.kind == "score")
    assert timeline.attrs["score"] in doc.scores
    assert doc.scores[timeline.attrs["score"]].format == "mei"
    assert doc.timelines[timeline.attrs["measure_table"]].kind == "beat"
    # Built from the MEI each time the file opens (FR-134).
    assert timeline.components == {}


def test_score_timelines_can_share_a_measure_table(tmp_path):
    doc = tla.read(EVERY_KIND)
    (first,) = (tl for tl in doc.timelines.values() if tl.kind == "score")
    other = mei_score(text_of(MEI))
    doc.scores[other.id] = other
    second = score_timeline(
        len(doc.timelines) + 1,
        score=other.id,
        measure_table=first.attrs["measure_table"],
    )
    doc.timelines[second.id] = second
    _, again = written_and_read(doc, tmp_path)
    attrs = again.timelines[second.id].attrs
    assert (attrs["score"], attrs["measure_table"]) == (
        other.id,
        first.attrs["measure_table"],
    )
    assert again.timelines[first.id].attrs == first.attrs


def test_a_score_timeline_without_a_score_or_measure_table_has_neither_key(tmp_path):
    # Before a score is imported: both at their default, null, left out.
    doc = tla.new_document()
    timeline = score_timeline(1)
    doc.timelines[timeline.id] = timeline
    data, again = written_and_read(doc, tmp_path)
    written = json.loads(data)["timelines"][timeline.id]
    assert "score" not in written and "measure_table" not in written
    attrs = again.timelines[timeline.id].attrs
    assert (attrs["score"], attrs["measure_table"]) == (None, None)
