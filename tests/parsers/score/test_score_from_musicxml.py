from tilia.parsers.score.musicxml import notes_from_musicXML
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components import Clef


def _import_with_patch(score_tl, beat_tl, data, tmp_path):
    tmp_file = tmp_path / "test.musicxml"
    tmp_file.write_text(data)
    errors = notes_from_musicXML(score_tl, beat_tl, str(tmp_file.resolve()))
    return errors


def test_example(score_tl, beat_tl, tmp_path):
    example = """<score-partwise version="3.1">
    <part-list>
        <score-part id="P1">
        <part-name>Piano</part-name>
        </score-part>
    </part-list>
    <part id="P1">
        <measure number="1">
        <attributes>
            <divisions>4</divisions>
            <key>
            <fifths>0</fifths>
            </key>
            <time>
            <beats>4</beats>
            <beat-type>4</beat-type>
            </time>
            <clef>
            <sign>G</sign>
            <line>2</line>
            </clef>
        </attributes>
        <note>
            <pitch>
            <step>C</step>
            <octave>4</octave>
            </pitch>
            <duration>16</duration>
            <type>whole</type>
        </note>
        </measure>
    </part>
    </score-partwise>
    """

    beat_tl.beat_pattern = [4]
    for i in range(5):
        beat_tl.create_beat(i)

    beat_tl.recalculate_measures()
    _import_with_patch(score_tl, beat_tl, example, tmp_path)

    clef = score_tl.get_component_by_attr("KIND", ComponentKind.CLEF)
    assert clef.staff_index == 0
    assert clef.time == 0
    assert clef.shorthand() == Clef.Shorthand.TREBLE

    key = score_tl.get_component_by_attr("KIND", ComponentKind.KEY_SIGNATURE)
    assert key.time == 0
    assert key.fifths == 0

    note = score_tl.get_component_by_attr("KIND", ComponentKind.NOTE)
    assert note.staff_index == 0
    assert note.start == 0
    assert note.end == 4
    assert note.step == 0
    assert note.accidental == 0
    assert note.octave == 4

    time_signature = score_tl.get_component_by_attr(
        "KIND", ComponentKind.TIME_SIGNATURE
    )
    assert time_signature.staff_index == 0
    assert time_signature.time == 0
    assert time_signature.numerator == 4
    assert time_signature.denominator == 4

    staff = score_tl.get_component_by_attr("KIND", ComponentKind.STAFF)
    assert staff.index == 0
    assert staff.line_count == 5
