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


def test_changing_attributes(score_tl, beat_tl, tmp_path):
    example = """<score-partwise version="4.0">
        <part-list>
            <score-part id="P1">
            <part-name>Flute</part-name>
            </score-part>
            </part-list>
        <part id="P1">
            <measure number="0" implicit="yes">
            <attributes>
                <divisions>2</divisions>
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
                <duration>2</duration>
                <tie type="start"/>
                <voice>1</voice>
                <type>quarter</type>
                <stem>up</stem>
                <notations>
                <tied type="start"/>
                </notations>
                </note>
            </measure>
            <measure number="1">
            <note>
                <pitch>
                <step>C</step>
                <octave>4</octave>
                </pitch>
                <duration>8</duration>
                <tie type="stop"/>
                <tie type="start"/>
                <voice>1</voice>
                <type>whole</type>
                <notations>
                <tied type="stop"/>
                <tied type="start"/>
                </notations>
                </note>
            </measure>
            <measure number="2">
            <attributes>
                <key>
                <fifths>-5</fifths>
                </key>
                <time>
                <beats>7</beats>
                <beat-type>8</beat-type>
                </time>
                <clef>
                <sign>F</sign>
                <line>4</line>
                </clef>
                </attributes>
            <note>
                <pitch>
                <step>C</step>
                <octave>4</octave>
                </pitch>
                <duration>7</duration>
                <tie type="stop"/>
                <tie type="start"/>
                <voice>1</voice>
                <type>half</type>
                <dot/>
                <dot/>
                <stem>down</stem>
                <notations>
                <tied type="stop"/>
                <tied type="start"/>
                </notations>
                </note>
            </measure>
            <measure number="3">
            <attributes>
                <key>
                <fifths>7</fifths>
                </key>
                <time>
                <beats>16</beats>
                <beat-type>4</beat-type>
                </time>
                <clef>
                <sign>C</sign>
                <line>3</line>
                </clef>
                </attributes>
            <note>
                <pitch>
                <step>C</step>
                <octave>4</octave>
                </pitch>
                <duration>32</duration>
                <tie type="stop"/>
                <voice>1</voice>
                <type>long</type>
                <stem>down</stem>
                <notations>
                <tied type="stop"/>
                </notations>
                </note>
            <barline location="right">
                <bar-style>light-heavy</bar-style>
                </barline>
            </measure>
            </part>
        </score-partwise>"""

    beat_tl.set_data("beat_pattern", [1])
    for i in range(5):
        beat_tl.create_beat(i)
    beat_tl.measure_numbers = [1, 2, 0, 3, 4]
    beat_tl.recalculate_measures()

    _import_with_patch(score_tl, beat_tl, example, tmp_path)

    assert (
        len(score_tl.component_manager._get_component_set_by_kind(ComponentKind.CLEF))
        == 4
    )
    for index, clef in enumerate(
        [Clef.ICON["G"], Clef.ICON["F"], Clef.ICON["G"], Clef.ICON["C"]]
    ):
        assert (
            score_tl.component_manager.get_component_by_attribute(
                "time", index, ComponentKind.CLEF
            ).icon
            == clef
        )

    assert (
        len(
            score_tl.component_manager._get_component_set_by_kind(
                ComponentKind.KEY_SIGNATURE
            )
        )
        == 4
    )
    for index, key in enumerate([0, -5, 0, 7]):
        assert (
            score_tl.component_manager.get_component_by_attribute(
                "time", index, ComponentKind.KEY_SIGNATURE
            ).fifths
            == key
        )

    assert (
        len(score_tl.component_manager._get_component_set_by_kind(ComponentKind.NOTE))
        == 4
    )
    for index in range(4):
        note = score_tl.component_manager.get_component_by_attribute(
            "start", index, ComponentKind.NOTE
        )
        assert note.accidental == 0
        assert note.octave == 4
        assert note.step == 0

    assert (
        len(
            score_tl.component_manager._get_component_set_by_kind(
                ComponentKind.TIME_SIGNATURE
            )
        )
        == 4
    )
    for index, actual_ts in enumerate([(4, 4), (7, 8), (4, 4), (16, 4)]):
        ts = score_tl.component_manager.get_component_by_attribute(
            "time", index, ComponentKind.TIME_SIGNATURE
        )
        assert ts.numerator == actual_ts[0]
        assert ts.denominator == actual_ts[1]
