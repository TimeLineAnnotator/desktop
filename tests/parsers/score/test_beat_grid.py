import pytest

from tilia.parsers.score.beat_grid import measures_from_musicxml


def _note(duration, chord=False):
    return (
        "<note>"
        + ("<chord/>" if chord else "")
        + f"<pitch><step>C</step><octave>4</octave></pitch><duration>{duration}</duration>"
        "</note>"
    )


def _attributes(divisions=None, beats=None, beat_type=None):
    inner = ""
    if divisions is not None:
        inner += f"<divisions>{divisions}</divisions>"
    if beats is not None:
        inner += (
            f"<time><beats>{beats}</beats><beat-type>{beat_type}</beat-type></time>"
        )
    return f"<attributes>{inner}</attributes>"


def _score(measures, header=""):
    body = "".join(measures)
    return f"""<score-partwise version="3.1">
    {header}
    <part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
    <part id="P1">{body}</part>
    </score-partwise>"""


def _measure(number, content, implicit=False):
    attrs = f' number="{number}"' + (' implicit="yes"' if implicit else "")
    return f"<measure{attrs}>{content}</measure>"


def _read(tmp_path, xml, name="test.musicxml"):
    path = tmp_path / name
    path.write_text(xml)
    return measures_from_musicxml(str(path))


def test_counts_beats_of_the_time_signature(tmp_path):
    xml = _score(
        [
            _measure(1, _attributes(1, 3, 4) + _note(3)),
            _measure(2, _note(3)),
        ]
    )
    measures, errors = _read(tmp_path, xml)

    assert not errors
    assert measures.numbers == [1, 2]
    assert measures.beat_counts == [3, 3]
    assert measures.beat_count == 6


def test_beats_follow_a_change_of_time_signature(tmp_path):
    xml = _score(
        [
            _measure(1, _attributes(2, 4, 4) + _note(8)),
            _measure(2, _attributes(beats=6, beat_type=8) + _note(6)),
        ]
    )
    measures, _ = _read(tmp_path, xml)

    assert measures.beat_counts == [4, 6]


def test_composite_beats_are_added(tmp_path):
    xml = _score([_measure(1, _attributes(2, "3+2", 8) + _note(5))])
    measures, _ = _read(tmp_path, xml)

    assert measures.beat_counts == [5]


def test_a_pickup_has_as_many_beats_as_its_notes(tmp_path):
    xml = _score(
        [
            _measure(0, _attributes(1, 4, 4) + _note(1), implicit=True),
            _measure(1, _note(4)),
        ]
    )
    measures, _ = _read(tmp_path, xml)

    assert measures.numbers == [0, 1]
    assert measures.beat_counts == [1, 4]


def test_other_implicit_measures_are_skipped(tmp_path):
    xml = _score(
        [
            _measure(1, _attributes(1, 4, 4) + _note(2)),
            _measure("X1", _note(2), implicit=True),
            _measure(2, _note(4)),
        ]
    )
    measures, errors = _read(tmp_path, xml)

    assert not errors
    assert measures.numbers == [1, 2]


def test_a_measure_its_notes_dont_fill_keeps_the_time_signature(tmp_path):
    xml = _score([_measure(1, _attributes(1, 3, 4)), _measure(2, _note(3))])
    measures, _ = _read(tmp_path, xml)

    assert measures.beat_counts == [3, 3]


def test_chords_and_voices_dont_lengthen_a_measure(tmp_path):
    content = (
        _attributes(1, 2, 4)
        + _note(2)
        + _note(2, chord=True)
        + "<backup><duration>2</duration></backup>"
        + _note(1)
        + _note(1)
    )
    measures, _ = _read(tmp_path, _score([_measure(1, content)]))

    assert measures.beat_counts == [2]


def test_without_time_signature_a_beat_is_a_quarter(tmp_path):
    xml = _score([_measure(1, _attributes(2) + _note(10))])
    measures, _ = _read(tmp_path, xml)

    assert measures.beat_counts == [5]


def test_seconds_per_beat_from_tempo(tmp_path):
    content = _attributes(1, 6, 8) + '<sound tempo="120"/>' + _note(3)
    measures, _ = _read(tmp_path, _score([_measure(1, content)]))

    assert measures.tempo == 120
    # Six eighths per measure: an eighth at 120 quarters per minute.
    assert measures.seconds_per_beat() == pytest.approx(0.25)


def test_seconds_per_beat_without_tempo(tmp_path):
    measures, _ = _read(tmp_path, _score([_measure(1, _attributes(1, 4, 4))]))

    assert measures.tempo is None
    assert measures.seconds_per_beat() == 1.0


def test_title_from_work(tmp_path):
    header = "<work><work-title>Limited Approximations</work-title></work>"
    measures, _ = _read(tmp_path, _score([_measure(1, "")], header))

    assert measures.title == "Limited Approximations"


def test_title_from_file_name(tmp_path):
    measures, _ = _read(tmp_path, _score([_measure(1, "")]), "in vain.musicxml")

    assert measures.title == "in vain"


@pytest.mark.parametrize(
    "xml, message",
    [
        ("<score-partwise><part-list/></score-partwise>", "no parts"),
        ("<notmusic/>", "not valid"),
        (_score([]), "no measures"),
        (_score([_measure("1a", "")]), "not a whole number"),
        ("<score-partwise", "can't read"),
    ],
)
def test_errors(tmp_path, xml, message):
    measures, errors = _read(tmp_path, xml)

    assert measures is None
    assert message in errors[0].lower()


def test_missing_file(tmp_path):
    measures, errors = measures_from_musicxml(str(tmp_path / "missing.musicxml"))

    assert measures is None
    assert errors
