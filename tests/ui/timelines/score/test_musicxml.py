from tests.mock import Serve
from tilia.parsers.score.musicxml import notes_from_musicXML
from tilia.requests import Get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components import Clef

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


def test_example(qtui, score_tl, beat_tl, tmp_path):
    beat_tl.beat_pattern = [4]
    for i in range(5):
        beat_tl.create_beat(i)

    beat_tl.recalculate_measures()

    tmp_file = tmp_path / 'test.musicxml'
    tmp_file.write_text(example)

    notes_from_musicXML(score_tl, beat_tl, str(tmp_file.resolve()))

    clef = score_tl.get_component_by_attr('KIND', ComponentKind.CLEF)
    assert clef.staff_index == 0
    assert clef.time == 0
    assert clef.shorthand() == Clef.Shorthand.TREBLE

    key = score_tl.get_component_by_attr('KIND', ComponentKind.KEY_SIGNATURE)
    assert key.time == 0
    assert key.fifths == 0

    note = score_tl.get_component_by_attr('KIND', ComponentKind.NOTE)
    assert note.staff_index == 0
    assert note.start == 0
    assert note.end == 4
    assert note.step == 0
    assert note.accidental == 0
    assert note.octave == 4

    time_signature = score_tl.get_component_by_attr('KIND', ComponentKind.TIME_SIGNATURE)
    assert time_signature.staff_index == 0
    assert time_signature.time == 0
    assert time_signature.numerator == 4
    assert time_signature.denominator == 4

    staff = score_tl.get_component_by_attr('KIND', ComponentKind.STAFF)
    assert staff.index == 0
    assert staff.line_count == 5


class TestInsertMeasureZero:
    XML = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
	<part-list>
		<score-part id="P1">
			<part-name>Violine</part-name>
		</score-part>
	</part-list>
	<part id="P1">
		<measure number="0" implicit="yes" width="153.12">
			<attributes>
				<divisions>4</divisions>
				<key>
					<fifths>0</fifths>
				</key>
				<time>
					<beats>3</beats>
					<beat-type>8</beat-type>
				</time>
				<clef>
					<sign>G</sign>
					<line>2</line>
				</clef>
			</attributes>
			<note default-x="94.57" default-y="-5">
				<pitch>
					<step>E</step>
					<octave>5</octave>
				</pitch>
				<duration>1</duration>
				<voice>1</voice>
				<type>16th</type>
				<stem>down</stem>
				<beam number="1">begin</beam>
				<beam number="2">begin</beam>
			</note>
			<note default-x="123.32" default-y="-10">
				<pitch>
					<step>D</step>
					<alter>1</alter>
					<octave>5</octave>
				</pitch>
				<duration>1</duration>
				<voice>1</voice>
				<type>16th</type>
				<accidental>sharp</accidental>
				<stem>down</stem>
				<beam number="1">end</beam>
				<beam number="2">end</beam>
			</note>
		</measure>
		<measure number="1" width="80">
			<note default-x="12.5" default-y="-5">
				<pitch>
					<step>E</step>
					<octave>5</octave>
				</pitch>
				<duration>6</duration>
				<voice>1</voice>
				<type>quarter</type>
				<dot default-x="30.49" default-y="-5"/>
				<stem>down</stem>
			</note>
		</measure>
		<measure number="2" width="80">
			<note default-x="12.5" default-y="-5">
				<pitch>
					<step>E</step>
					<octave>5</octave>
				</pitch>
				<duration>6</duration>
				<voice>1</voice>
				<type>quarter</type>
				<dot default-x="30.49" default-y="-5"/>
				<stem>down</stem>
			</note>
			<barline location="right">
				<bar-style>light-heavy</bar-style>
			</barline>
		</measure>
	</part>
</score-partwise>
"""

    def xml_path(self, tmp_path):
        tmp_file = tmp_path / 'test.musicxml'
        tmp_file.write_text(self.XML)
        return str(tmp_file.resolve())

    def setup_valid_beats(self, beat_tl):
        beat_tl.beat_pattern = [3]

        for i in range(5, 12):
            beat_tl.create_beat(i)

        beat_tl.recalculate_measures()

    def test_user_accpets(self, qtui, score_tlui, beat_tl, tmp_path, tilia_state):
        self.setup_valid_beats(beat_tl)

        with Serve(Get.FROM_USER_YES_OR_NO, True):
            notes_from_musicXML(score_tlui.timeline, beat_tl, self.xml_path(tmp_path))

        clefs = score_tlui.timeline.get_components_by_attr('KIND', ComponentKind.CLEF)
        assert len(clefs) == 1

        notes = score_tlui.timeline.get_components_by_attr('KIND', ComponentKind.NOTE)
        assert len(notes) == 4

        time_signatures = score_tlui.timeline.get_components_by_attr('KIND', ComponentKind.TIME_SIGNATURE)
        assert len(time_signatures) == 1

        assert beat_tl.measure_numbers[0] == 0
        assert beat_tl._beats_in_measure[0] == 1

    def test_user_accepts_but_no_space_for_measure(self, qtui, score_tlui, beat_tl, tmp_path, tilia_state):
        beat_tl.fill_with_beats(beat_tl.FillMethod.BY_AMOUNT, 10)

        with Serve(Get.FROM_USER_YES_OR_NO, True):
            notes_from_musicXML(score_tlui.timeline, beat_tl, self.xml_path(tmp_path))

        assert len(score_tlui) == 0

    def test_user_accepts_but_less_than_two_measure_in_beat_timeline(self, qtui, score_tlui, beat_tl, tmp_path,
                                                                     tilia_state):
        beat_tl.beat_pattern = [2]
        beat_tl.create_beat(5)
        beat_tl.create_beat(6)
        beat_tl.recalculate_measures()

        with Serve(Get.FROM_USER_YES_OR_NO, True):
            notes_from_musicXML(score_tlui.timeline, beat_tl, self.xml_path(tmp_path))

        assert len(score_tlui) == 0

    def test_user_rejects(self, qtui, score_tlui, beat_tl, tmp_path, tilia_state):
        self.setup_valid_beats(beat_tl)

        with Serve(Get.FROM_USER_YES_OR_NO, False):
            notes_from_musicXML(score_tlui.timeline, beat_tl, self.xml_path(tmp_path))

        assert len(score_tlui) == 0

    def test_no_beat_1(self, qtui, score_tlui, beat_tl, tmp_path, tilia_state):
        self.setup_valid_beats(beat_tl)

        beat_tl.set_measure_number(0, 2)

        notes_from_musicXML(score_tlui.timeline, beat_tl, self.xml_path(tmp_path))

        # no prompt for measure 0 as there is no measure 1
        # and measure 2 should have been imported
        notes = score_tlui.timeline.get_components_by_attr('KIND', ComponentKind.NOTE)
        assert len(notes) == 1
