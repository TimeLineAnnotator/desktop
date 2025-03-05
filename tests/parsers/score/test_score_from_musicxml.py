from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QMessageBox

from tilia.parsers.score.musicxml import notes_from_musicXML
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components import Clef, Note
from tilia.timelines.score.timeline import ScoreTimeline


def _import_with_patch(score_tl, beat_tl, data, tmp_path):
    tmp_file = tmp_path / "test.musicxml"
    tmp_file.write_text(data)
    errors = notes_from_musicXML(score_tl, beat_tl, str(tmp_file.resolve()))
    return errors


def _get_components_by_kind(
    score_tl: ScoreTimeline, kind: ComponentKind
) -> list[ComponentKind]:
    return list(sorted(score_tl.component_manager._get_component_set_by_kind(kind)))


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
            <measure number="3">
            <attributes>
                <key>
                <fifths>7</fifths>
                </key>
                </attributes>
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
            <measure number="4">
            <attributes>
                <time>
                <beats>7</beats>
                <beat-type>8</beat-type>
                </time>
                </attributes>
            <note>
                <pitch>
                <step>C</step>
                <octave>4</octave>
                </pitch>
                <duration>7</duration>
                <tie type="stop"/>
                <voice>1</voice>
                <type>half</type>
                <dot/>
                <dot/>
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
    for i in range(6):
        beat_tl.create_beat(i)
    beat_tl.measure_numbers = [1, 3, 0, 2, 4, 5]
    beat_tl.recalculate_measures()

    _import_with_patch(score_tl, beat_tl, example, tmp_path)

    assert (
        len(score_tl.component_manager._get_component_set_by_kind(ComponentKind.CLEF))
        == 4
    )
    for time, clef in {
        0: Clef.ICON["G"],
        1: Clef.ICON["F"],
        2: Clef.ICON["G"],
        3: Clef.ICON["F"],
    }.items():
        assert (
            score_tl.component_manager.get_component_by_attribute(
                "time", time, ComponentKind.CLEF
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
    for time, key_sig in {0: 0, 1: 7, 2: 0, 4: 7}.items():
        assert (
            score_tl.component_manager.get_component_by_attribute(
                "time", time, ComponentKind.KEY_SIGNATURE
            ).fifths
            == key_sig
        )

    assert (
        len(score_tl.component_manager._get_component_set_by_kind(ComponentKind.NOTE))
        == 5
    )
    for time in range(5):
        note = score_tl.component_manager.get_component_by_attribute(
            "start", time, ComponentKind.NOTE
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
        == 3
    )
    for index, time_sig in {0: (4, 4), 2: (4, 4), 4: (7, 8)}.items():
        ts = score_tl.component_manager.get_component_by_attribute(
            "time", index, ComponentKind.TIME_SIGNATURE
        )
        assert ts.numerator == time_sig[0]
        assert ts.denominator == time_sig[1]


class TestMeasureZeroNotInTimeline:
    xml = """<score-partwise version="4.0">
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
                </part>
            </score-partwise>"""

    def test_user_accepts_measure_zero_import(self, qtui, beat_tl, score_tl, tmp_path):

        beat_tl.set_data("beat_pattern", [1])
        beat_tl.create_beat(1)
        beat_tl.create_beat(2)
        beat_tl.recalculate_measures()

        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes
        ):
            _import_with_patch(score_tl, beat_tl, self.xml, tmp_path)

        notes = _get_components_by_kind(score_tl, ComponentKind.NOTE)
        assert len(notes) == 2
        assert notes[0].start_measure == 0
        assert notes[1].start_measure == 1
        clefs = _get_components_by_kind(score_tl, ComponentKind.CLEF)
        assert len(clefs) == 1
        assert clefs[0].measure == 0

    def test_user_refuses_measure_zero_import(self, qtui, beat_tl, score_tl, tmp_path):
        beat_tl.set_data("beat_pattern", [1])
        beat_tl.create_beat(1)
        beat_tl.create_beat(2)
        beat_tl.recalculate_measures()

        with patch.object(
            QMessageBox, "question", return_value=QMessageBox.StandardButton.No
        ):
            _import_with_patch(score_tl, beat_tl, self.xml, tmp_path)

        notes = _get_components_by_kind(score_tl, ComponentKind.NOTE)
        assert len(notes) == 1
        assert notes[0].start_measure == 1
        # clef gets "pushed" to first measure
        clefs = _get_components_by_kind(score_tl, ComponentKind.CLEF)
        assert len(clefs) == 1
        assert clefs[0].measure == 1
        assert clefs[0].beat == 1


class TestTremolo:
    def test_two_note_tremolo(self, qtui, beat_tl, score_tl, tmp_path):
        xml = """<score-partwise version="4.0">
                <part-list>
                    <score-part id="P1">
                    <part-name>Flute</part-name>
                    </score-part>
                    </part-list>
                <part id="P1">
                    <measure number="1">
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
                        <duration>4</duration>
                        <voice>1</voice>
                        <type>quarter</type>
                        <time-modification>
                            <actual-notes>2</actual-notes>
                            <normal-notes>1</normal-notes>
                            </time-modification>
                        <stem>up</stem>
                        <notations>
                            <ornaments>
                                <tremolo type="start">2</tremolo>
                                </ornaments>
                            </notations>
                        </note>
                    <direction>
                        <direction-type>
                            <direction-type-name>continue</direction-type-name>
                            </direction-type>
                        </direction>
                    <note>
                        <pitch>
                          <step>F</step>
                          <alter>1</alter>
                          <octave>4</octave>
                          </pitch>
                        <duration>6</duration>
                        <type>quarter</type>
                        <time-modification>
                          <actual-notes>2</actual-notes>
                          <normal-notes>1</normal-notes>
                          </time-modification>
                        <stem>up</stem>
                        <notations>
                          <ornaments>
                            <tremolo type="stop">2</tremolo>
                            </ornaments>
                          </notations>
                        </note>
                        </measure>
                    </part>
                </score-partwise>"""
        # <direction> is added to ensure we are not assuming that the next element is a note

        beat_tl.set_data("beat_pattern", [1])
        beat_tl.create_beat(1)
        beat_tl.create_beat(2)
        beat_tl.recalculate_measures()

        _import_with_patch(score_tl, beat_tl, xml, tmp_path)

        notes = _get_components_by_kind(score_tl, ComponentKind.NOTE)
        assert len(notes) == 4
        assert [n.start for n in notes] == [1, 1.25, 1.5, 1.75]
        assert [n.end for n in notes] == [1.25, 1.5, 1.75, 2]
        assert [n.step for n in notes] == [0, 3, 0, 3]
        assert [n.octave for n in notes] == [4, 4, 4, 4]
        assert [n.staff_index for n in notes] == [0, 0, 0, 0]

        # do not parse one note tromlos like this
        # test cases where denominator is not 4
        # test cases where denominator is not 4

    @pytest.mark.parametrize("flag_count", [1, 2, 3])
    @pytest.mark.parametrize("time_sig_denominator", [2, 4, 8])
    @pytest.mark.parametrize("note_duration", [4, 8, 16])
    @pytest.mark.parametrize("divisions", [4])
    def test_one_note_tremolo(
        self,
        flag_count,
        time_sig_denominator,
        note_duration,
        divisions,
        qtui,
        beat_tl,
        score_tl,
        tmp_path,
    ):
        ic(flag_count, time_sig_denominator, note_duration, divisions)
        if (flag_count, time_sig_denominator) == (1, 2):
            pytest.skip("Tremolos larger than a measure do not exist.")
        note_xml = f"""<note>
                        <pitch>
                            <step>C</step>
                            <octave>4</octave>
                        </pitch>
                        <duration>{note_duration}</duration>
                        <type>quarter</type>
                        <notations>
                            <ornaments>
                                <tremolo type="single">{flag_count}</tremolo>
                                </ornaments>
                            </notations>
                        </note>"""
        quarters_per_measure = 4 * 4 // time_sig_denominator
        note_per_quarter = note_duration // divisions
        xml = f"""<score-partwise version="4.0">
                        <part-list>
                            <score-part id="P1">
                            <part-name>Flute</part-name>
                            </score-part>
                            </part-list>
                        <part id="P1">
                            <measure number="1">
                            <attributes>
                                <divisions>{divisions}</divisions>
                                <key>
                                    <fifths>0</fifths>
                                    </key>
                                <time>
                                    <beats>4</beats>
                                    <beat-type>{time_sig_denominator}</beat-type>
                                    </time>
                                <clef>
                                    <sign>G</sign>
                                    <line>2</line>
                                    </clef>
                                </attributes>
                                {note_xml*quarters_per_measure*note_per_quarter}
                                </measure>
                            </part>
                        </score-partwise>"""

        beat_tl.set_data("beat_pattern", [4])
        measure_seconds = 4
        for i in range(measure_seconds + 1):
            beat_tl.create_beat(i)
        beat_tl.recalculate_measures()

        _import_with_patch(score_tl, beat_tl, xml, tmp_path)

        beats_per_quarter = time_sig_denominator / 4
        beats_per_full_tremolo = beats_per_quarter * note_duration / divisions
        beat_duration = 1 / beats_per_quarter * divisions
        full_tremolo_duration = beats_per_full_tremolo * beat_duration
        full_tremolo_per_beat = 1 / beats_per_full_tremolo
        beats_per_seconds = measure_seconds / 4
        full_tremolo_seconds = beats_per_seconds * full_tremolo_per_beat

        note_count = int((2**flag_count) * full_tremolo_duration / divisions)

        notes: list[Note] = _get_components_by_kind(score_tl, ComponentKind.NOTE)
        assert len(notes) == note_count * quarters_per_measure * note_duration / 4
        # assert [n.start for n in notes] == [
        #     i / note_count * full_tremolo_seconds for i in range(note_count)
        # ]
        # assert [n.end for n in notes] == [
        #     (i + 1) / note_count * full_tremolo_seconds for i in range(note_count)
        # ]
        #
        # assert all([n.step == 0 for n in notes])
        # assert all([n.octave == 4 for n in notes])
        # assert all([n.staff_index == 0 for n in notes])
