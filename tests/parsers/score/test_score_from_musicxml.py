import pytest

from tests.mock import patch_yes_or_no_dialog
from tilia.parsers.score.musicxml import notes_from_musicXML
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.components import Clef
from tilia.timelines.score.timeline import ScoreTimeline


def _import_with_patch(score_tl, beat_tl, data, tmp_path):
    tmp_file = tmp_path / "test.musicxml"
    tmp_file.write_text(data)
    errors = notes_from_musicXML(score_tl, beat_tl, str(tmp_file.resolve()))
    return errors


def test_import_with_empty_beat_timeline(score_tl, beat_tl, tmp_path):
    xml = """<score-partwise version="3.1">
    <part-list>
        <score-part id="P1"><part-name>Piano</part-name></score-part>
    </part-list>
    <part id="P1"><measure number="1"></measure></part>
    </score-partwise>
    """

    success, errors = _import_with_patch(score_tl, beat_tl, xml, tmp_path)

    assert not success
    assert errors
    assert "no beats" in errors[0].lower()


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
    assert time_signature.numerator == "4"
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
    beat_tl.set_measure_numbers([1, 3, 0, 2, 4, 5])
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
    for index, time_sig in {0: ("4", 4), 2: ("4", 4), 4: ("7", 8)}.items():
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

        with patch_yes_or_no_dialog(True):
            _import_with_patch(score_tl, beat_tl, self.xml, tmp_path)

        notes = _get_components_by_kind(score_tl, ComponentKind.NOTE)
        assert len(notes) == 2
        assert notes[0].start_measure == 0
        assert notes[1].start_measure == 1
        clefs = _get_components_by_kind(score_tl, ComponentKind.CLEF)
        assert len(clefs) == 1
        assert clefs[0].measure == 0

    def test_user_accepts_measure_zero_import_with_no_measure_2(
        self, qtui, beat_tl, score_tl, tmp_path
    ):
        beat_tl.set_data("beat_pattern", [1])
        beat_tl.create_beat(1)
        beat_tl.create_beat(2)
        beat_tl.create_beat(3)
        beat_tl.measure_numbers = [1, 3, 4]
        beat_tl.recalculate_measures()

        with patch_yes_or_no_dialog(True):
            success, errors = _import_with_patch(score_tl, beat_tl, self.xml, tmp_path)

        assert success
        assert errors == []
        # A quarter of the first measure, which lasts 1 s, before its 1 s.
        assert beat_tl[0].time == 0.75
        notes = _get_components_by_kind(score_tl, ComponentKind.NOTE)
        assert [note.start_measure for note in notes] == [0, 1]

    def test_user_refuses_measure_zero_import(self, qtui, beat_tl, score_tl, tmp_path):
        beat_tl.set_data("beat_pattern", [1])
        beat_tl.create_beat(1)
        beat_tl.create_beat(2)
        beat_tl.recalculate_measures()

        with patch_yes_or_no_dialog(False):
            _import_with_patch(score_tl, beat_tl, self.xml, tmp_path)

        notes = _get_components_by_kind(score_tl, ComponentKind.NOTE)
        assert len(notes) == 1
        assert notes[0].start_measure == 1
        # clef gets "pushed" to first measure
        clefs = _get_components_by_kind(score_tl, ComponentKind.CLEF)
        assert len(clefs) == 1
        assert clefs[0].measure == 1
        assert clefs[0].beat == 1


def test_import_in_last_measure(qtui, beat_tl, score_tl, tmp_path):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
    <part-list>
        <score-part id="P1">
            <part-name>Violine</part-name>
        </score-part>
    </part-list>
    <part id="P1">
        <measure number="1" width="80">
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
                <duration>3</duration>
                <voice>1</voice>
                <type>quarter</type>
                <dot default-x="30.49" default-y="-5"/>
                <stem>down</stem>
            </note>
            <note default-x="12.5" default-y="-5">
                <pitch>
                    <step>E</step>
                    <octave>5</octave>
                </pitch>
                <duration>3</duration>
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

    beat_tl.set_data("beat_pattern", [1])
    beat_tl.create_beat(1)
    beat_tl.create_beat(2)
    beat_tl.recalculate_measures()

    _import_with_patch(score_tl, beat_tl, xml, tmp_path)

    notes = _get_components_by_kind(score_tl, ComponentKind.NOTE)
    assert len(notes) == 3


SCORE_ATTRIBUTES = {
    "key": "<key><fifths>0</fifths></key>",
    "time": "<time><beats>4</beats><beat-type>4</beat-type></time>",
    "clef": "<clef><sign>G</sign><line>2</line></clef>",
}
ATTRIBUTE_KINDS = {
    "key": ComponentKind.KEY_SIGNATURE,
    "time": ComponentKind.TIME_SIGNATURE,
    "clef": ComponentKind.CLEF,
}


def _measure(attributes: str) -> str:
    """A measure's contents: its attributes, then a whole note."""
    return f"""<attributes><divisions>4</divisions>{attributes}</attributes>
        <note>
            <pitch><step>C</step><octave>4</octave></pitch>
            <duration>16</duration>
            <type>whole</type>
        </note>"""


def _score_with_measures(*measures: str) -> str:
    measures = "".join(
        f'<measure number="{number}">{contents}</measure>'
        for number, contents in enumerate(measures, start=1)
    )
    return f"""<score-partwise version="4.0">
    <part-list>
        <score-part id="P1"><part-name>Piano</part-name></score-part>
    </part-list>
    <part id="P1">{measures}</part>
    </score-partwise>
    """


def _attributes_without(missing: str) -> str:
    return "".join(v for k, v in SCORE_ATTRIBUTES.items() if k != missing)


@pytest.mark.parametrize(
    "missing, replacement",
    [
        ("key", ""),
        ("time", ""),
        ("time", "<time><senza-misura/></time>"),
        ("clef", ""),
        ("clef", "<clef><sign>none</sign></clef>"),
    ],
    ids=["no key", "no time signature", "senza misura", "no clef", "none clef"],
)
def test_score_without_an_attribute(missing, replacement, score_tl, beat_tl, tmp_path):
    # Scores often have no key signature (atonal music, percussion), and
    # some have no time signature or clef. A none clef is shown as if in
    # treble clef, as the file asks, so it isn't reported.
    beat_tl.beat_pattern = [4]
    for i in range(5):
        beat_tl.create_beat(i)
    beat_tl.recalculate_measures()

    success, errors = _import_with_patch(
        score_tl,
        beat_tl,
        _score_with_measures(_measure(_attributes_without(missing) + replacement)),
        tmp_path,
    )

    assert success
    assert errors == []
    assert not _get_components_by_kind(score_tl, ATTRIBUTE_KINDS[missing])
    assert _get_components_by_kind(score_tl, ComponentKind.NOTE)


def test_percussion_clef_is_reported_as_not_implemented(score_tl, beat_tl, tmp_path):
    # TiLiA draws no percussion clef. The notes are placed as in treble clef.
    beat_tl.beat_pattern = [4]
    for i in range(5):
        beat_tl.create_beat(i)
    beat_tl.recalculate_measures()
    percussion = "<clef><sign>percussion</sign></clef>"

    success, errors = _import_with_patch(
        score_tl,
        beat_tl,
        _score_with_measures(_measure(_attributes_without("clef") + percussion)),
        tmp_path,
    )

    assert success
    assert errors == ["<clef> - percussion not implemented"]


@pytest.mark.parametrize("attribute", ["key", "time", "clef"])
def test_attribute_first_given_after_the_first_measure(
    attribute, score_tl, beat_tl, tmp_path
):
    # The measures before it have none, as in a score with none at all.
    beat_tl.beat_pattern = [4]
    for i in range(9):
        beat_tl.create_beat(i)
    beat_tl.recalculate_measures()

    success, errors = _import_with_patch(
        score_tl,
        beat_tl,
        _score_with_measures(
            _measure(_attributes_without(attribute)),
            _measure(SCORE_ATTRIBUTES[attribute]),
        ),
        tmp_path,
    )

    assert success
    assert errors == []
    components = _get_components_by_kind(score_tl, ATTRIBUTE_KINDS[attribute])
    assert [c.get_data("time") for c in components] == [4]


def test_octave_clef(score_tl, beat_tl, tmp_path):
    # A treble-8vb clef, as for tenor voice or guitar.
    beat_tl.beat_pattern = [4]
    for i in range(5):
        beat_tl.create_beat(i)
    beat_tl.recalculate_measures()
    clef = (
        "<clef><sign>G</sign><line>2</line>"
        "<clef-octave-change>-1</clef-octave-change></clef>"
    )

    _import_with_patch(
        score_tl,
        beat_tl,
        _score_with_measures(_measure(_attributes_without("clef") + clef)),
        tmp_path,
    )

    (clef,) = _get_components_by_kind(score_tl, ComponentKind.CLEF)
    assert clef.shorthand() == Clef.Shorthand.TREBLE_8VB
    assert clef.icon == "clef-treble-8vb"


def test_non_traditional_key_is_reported_as_not_implemented(
    score_tl, beat_tl, tmp_path
):
    # TiLiA's key signatures only have fifths.
    beat_tl.beat_pattern = [4]
    for i in range(5):
        beat_tl.create_beat(i)
    beat_tl.recalculate_measures()
    key = (
        "<key><key-step>B</key-step><key-alter>-1</key-alter>"
        "<key-step>F</key-step><key-alter>1</key-alter></key>"
    )

    success, errors = _import_with_patch(
        score_tl,
        beat_tl,
        _score_with_measures(_measure(_attributes_without("key") + key)),
        tmp_path,
    )

    assert success
    assert errors == ["<key> - non-traditional key not implemented"]
    assert not _get_components_by_kind(score_tl, ComponentKind.KEY_SIGNATURE)
    assert _get_components_by_kind(score_tl, ComponentKind.NOTE)


@pytest.mark.timeout(10)
def test_notes_in_a_measure_the_beat_timeline_skips_are_not_imported(
    score_tl, beat_tl, tmp_path
):
    # As notes after the beat timeline's last measure.
    beat_tl.set_data("beat_pattern", [1])
    for i in range(4):
        beat_tl.create_beat(i)
    beat_tl.set_measure_numbers([1, 3, 4, 5])
    beat_tl.recalculate_measures()

    success, errors = _import_with_patch(
        score_tl,
        beat_tl,
        _score_with_measures(
            _measure("".join(SCORE_ATTRIBUTES.values())), _measure(""), _measure("")
        ),
        tmp_path,
    )

    assert success
    assert errors == []
    notes = _get_components_by_kind(score_tl, ComponentKind.NOTE)
    assert [(n.get_data("start"), n.get_data("end")) for n in notes] == [
        (0, 1),
        (1, 2),
    ]
    bar_lines = _get_components_by_kind(score_tl, ComponentKind.BAR_LINE)
    assert [bar_line.get_data("time") for bar_line in bar_lines] == [1, 2]


def test_a_measure_before_a_repeat_ends_with_a_bar_line(score_tl, beat_tl, tmp_path):
    # Each pass through a measure ends with a bar line, whatever measure
    # follows it.
    beat_tl.set_data("beat_pattern", [1])
    for i in range(4):
        beat_tl.create_beat(i)
    beat_tl.measure_numbers = [1, 2, 1, 2]
    beat_tl.recalculate_measures()

    success, errors = _import_with_patch(
        score_tl,
        beat_tl,
        _score_with_measures(
            _measure("".join(SCORE_ATTRIBUTES.values())), _measure("")
        ),
        tmp_path,
    )

    assert success
    assert errors == []
    bar_lines = _get_components_by_kind(score_tl, ComponentKind.BAR_LINE)
    assert [bar_line.get_data("time") for bar_line in bar_lines] == [1, 2, 3, 4]


def test_the_last_measure_ends_with_a_bar_line(score_tl, beat_tl, tmp_path):
    # The last beat lasts as long as the gap before it, and the last measure's
    # notes end there too.
    beat_tl.set_data("beat_pattern", [1])
    for i in range(3):
        beat_tl.create_beat(i)
    beat_tl.recalculate_measures()

    success, errors = _import_with_patch(
        score_tl,
        beat_tl,
        _score_with_measures(
            _measure("".join(SCORE_ATTRIBUTES.values())), _measure(""), _measure("")
        ),
        tmp_path,
    )

    assert success
    assert errors == []
    notes = _get_components_by_kind(score_tl, ComponentKind.NOTE)
    assert notes[-1].get_data("end") == 3
    bar_lines = _get_components_by_kind(score_tl, ComponentKind.BAR_LINE)
    assert [bar_line.get_data("time") for bar_line in bar_lines] == [1, 2, 3]


QUARTER_NOTE = """<note>
            <pitch><step>C</step><octave>4</octave></pitch>
            <duration>4</duration>
            <type>quarter</type>
        </note>"""
QUARTER_REST = """<note><rest/><duration>4</duration><type>quarter</type></note>"""


def _measure_of_quarters(attributes: str, notes: int = 4, rests: int = 0) -> str:
    """A measure's contents: its attributes, then that many quarter notes, then
    that many quarter rests."""
    return (
        f"<attributes><divisions>4</divisions>{attributes}</attributes>"
        + QUARTER_NOTE * notes
        + QUARTER_REST * rests
    )


def _bar_line_times(score_tl) -> list[float]:
    bar_lines = _get_components_by_kind(score_tl, ComponentKind.BAR_LINE)
    return [bar_line.get_data("time") for bar_line in bar_lines]


def _note_times(score_tl) -> list[tuple[float, float]]:
    notes = _get_components_by_kind(score_tl, ComponentKind.NOTE)
    return [(n.get_data("start"), n.get_data("end")) for n in notes]


def _create_beats(beat_tl, times: list[float], beat_pattern: list[int]) -> None:
    beat_tl.set_data("beat_pattern", beat_pattern)
    for time in times:
        beat_tl.create_beat(time)
    beat_tl.recalculate_measures()


class TestLastMeasureEnd:
    """The last beat lasts as long as the gap before it."""

    @pytest.mark.parametrize("duration", [12, 100])
    def test_ritardando(self, score_tl, beat_tl, tilia_state, tmp_path, duration):
        tilia_state.set_duration(duration, scale_timelines="no")
        _create_beats(beat_tl, [0, 1, 2, 3, 4, 6, 8, 10], [4])

        success, errors = _import_with_patch(
            score_tl,
            beat_tl,
            _score_with_measures(
                _measure_of_quarters("".join(SCORE_ATTRIBUTES.values())),
                _measure_of_quarters(""),
            ),
            tmp_path,
        )

        assert success
        assert errors == []
        notes = _note_times(score_tl)
        assert len(notes) == 8
        assert notes[-1] == (10, 12)
        assert _bar_line_times(score_tl) == [4, 12]

    def test_last_measure_with_more_beats_than_the_one_before(
        self, score_tl, beat_tl, tmp_path
    ):
        _create_beats(beat_tl, list(range(7)), [3, 4])

        success, errors = _import_with_patch(
            score_tl,
            beat_tl,
            _score_with_measures(
                _measure_of_quarters("".join(SCORE_ATTRIBUTES.values()), notes=3),
                _measure_of_quarters(""),
            ),
            tmp_path,
        )

        assert success
        assert errors == []
        notes = _note_times(score_tl)
        assert len(notes) == 7
        assert notes[-1] == (6, 7)
        assert _bar_line_times(score_tl) == [3, 7]

    def test_two_beats_tapped_in_a_measure_of_four(self, score_tl, beat_tl, tmp_path):
        _create_beats(beat_tl, [0, 1, 2, 3, 4, 5], [4])

        success, errors = _import_with_patch(
            score_tl,
            beat_tl,
            _score_with_measures(
                _measure_of_quarters("".join(SCORE_ATTRIBUTES.values())),
                _measure_of_quarters(""),
            ),
            tmp_path,
        )

        assert success
        assert errors == []
        assert _note_times(score_tl)[-4:] == [(4, 4.5), (4.5, 5), (5, 5.5), (5.5, 6)]
        assert _bar_line_times(score_tl) == [4, 6]

    def test_steady_last_measure(self, score_tl, beat_tl, tmp_path):
        _create_beats(beat_tl, list(range(8)), [4])

        success, errors = _import_with_patch(
            score_tl,
            beat_tl,
            _score_with_measures(
                _measure_of_quarters("".join(SCORE_ATTRIBUTES.values())),
                _measure_of_quarters(""),
            ),
            tmp_path,
        )

        assert success
        assert errors == []
        assert _note_times(score_tl)[-1] == (7, 8)
        assert _bar_line_times(score_tl) == [4, 8]

    @pytest.mark.parametrize(
        "duration, last_note, bar_line",
        [
            pytest.param(100, (3, 4), 4, id="before the media's end"),
            pytest.param(3.5, (3, 3.5), 3.5, id="past the media's end"),
        ],
    )
    def test_timeline_with_one_measure_has_an_end(
        self, score_tl, beat_tl, tilia_state, tmp_path, duration, last_note, bar_line
    ):
        tilia_state.set_duration(duration, scale_timelines="no")
        _create_beats(beat_tl, [0, 1, 2, 3], [4])

        success, errors = _import_with_patch(
            score_tl,
            beat_tl,
            _score_with_measures(
                _measure_of_quarters("".join(SCORE_ATTRIBUTES.values()))
            ),
            tmp_path,
        )

        assert success
        assert errors == []
        notes = _note_times(score_tl)
        assert len(notes) == 4
        assert notes[-1] == last_note
        assert _bar_line_times(score_tl) == [bar_line]

    def test_timeline_with_one_beat_has_nothing_to_measure_by(
        self, score_tl, beat_tl, tmp_path
    ):
        _create_beats(beat_tl, [0], [1])

        success, errors = _import_with_patch(
            score_tl,
            beat_tl,
            _score_with_measures(_measure("".join(SCORE_ATTRIBUTES.values()))),
            tmp_path,
        )

        assert success
        assert errors == []
        assert _note_times(score_tl) == []
        assert _bar_line_times(score_tl) == []


class TestLastMeasureEndsAtTheMediaEnd:
    """A last measure's end stops at the media's end."""

    @staticmethod
    def _create_one_beat_measures(beat_tl, amount: int) -> None:
        _create_beats(beat_tl, list(range(amount)), [1])

    @staticmethod
    def _fill_four_beat_measures(beat_tl) -> None:
        beat_tl.set_data("beat_pattern", [4])
        beat_tl.fill_with_beats(BeatTimeline.FillMethod.BY_AMOUNT, 16)

    def test_note_running_past_the_media_end_is_cut_there(
        self, score_tl, beat_tl, tilia_state, tmp_path
    ):
        tilia_state.set_duration(2.5, scale_timelines="no")
        self._create_one_beat_measures(beat_tl, 3)

        success, errors = _import_with_patch(
            score_tl,
            beat_tl,
            _score_with_measures(
                _measure("".join(SCORE_ATTRIBUTES.values())),
                _measure(""),
                _measure(""),
            ),
            tmp_path,
        )

        assert success
        assert errors == []
        assert _note_times(score_tl) == [(0, 1), (1, 2), (2, 2.5)]
        assert _bar_line_times(score_tl) == [1, 2, 2.5]

    def test_time_after_the_last_beat_fits_itself_to_the_media_end(
        self, score_tl, beat_tl, tilia_state, tmp_path
    ):
        tilia_state.set_duration(2.5, scale_timelines="no")
        self._create_one_beat_measures(beat_tl, 3)

        success, errors = _import_with_patch(
            score_tl,
            beat_tl,
            _score_with_measures(
                _measure("".join(SCORE_ATTRIBUTES.values())),
                _measure(""),
                _measure_of_quarters("", notes=1, rests=3),
            ),
            tmp_path,
        )

        assert success
        assert errors == []
        # A quarter of the half second left, not of the second it would last.
        assert _note_times(score_tl)[-1] == (2, 2.125)
        assert _bar_line_times(score_tl) == [1, 2, 2.5]

    @pytest.mark.parametrize(
        "duration",
        [
            # The last measure's end computes as 61.300000000000004.
            61.3,
            # And as 61.699999999999996, just before the media's end.
            61.7,
        ],
    )
    def test_rounding_gives_no_error(
        self, score_tl, beat_tl, tilia_state, tmp_path, duration
    ):
        tilia_state.set_duration(duration, scale_timelines="no")
        self._fill_four_beat_measures(beat_tl)

        success, errors = _import_with_patch(
            score_tl,
            beat_tl,
            _score_with_measures(
                _measure("".join(SCORE_ATTRIBUTES.values())),
                _measure(""),
                _measure(""),
                _measure_of_quarters("", notes=1, rests=3),
            ),
            tmp_path,
        )

        assert success
        assert errors == []
        assert _bar_line_times(score_tl)[-1] == pytest.approx(duration)

    @pytest.mark.parametrize(
        "duration", [61.7, 300.3, 421.296, 291.974, 100.0, 61.3, 73.1, 19.9]
    )
    def test_rounding_loses_no_note(
        self, score_tl, beat_tl, tilia_state, tmp_path, duration
    ):
        tilia_state.set_duration(duration, scale_timelines="no")
        self._fill_four_beat_measures(beat_tl)

        success, errors = _import_with_patch(
            score_tl,
            beat_tl,
            _score_with_measures(
                _measure_of_quarters("".join(SCORE_ATTRIBUTES.values())),
                _measure_of_quarters(""),
                _measure_of_quarters(""),
                _measure_of_quarters(""),
            ),
            tmp_path,
        )

        assert success
        assert errors == []
        notes = _note_times(score_tl)
        assert len(notes) == 16
        assert notes[-1][1] == pytest.approx(duration)

    def test_last_measure_that_ends_before_the_media_end_does_not_change(
        self, score_tl, beat_tl, tilia_state, tmp_path
    ):
        tilia_state.set_duration(10, scale_timelines="no")
        self._create_one_beat_measures(beat_tl, 3)

        success, errors = _import_with_patch(
            score_tl,
            beat_tl,
            _score_with_measures(
                _measure("".join(SCORE_ATTRIBUTES.values())),
                _measure(""),
                _measure(""),
            ),
            tmp_path,
        )

        assert success
        assert errors == []
        assert _note_times(score_tl)[-1] == (2, 3)
        assert _bar_line_times(score_tl) == [1, 2, 3]


class TestLastMeasureNeverEndsBeforeItsLastBeat:
    """With the media's end at or before the last beat, the last measure ends on
    that beat. A note left with no length is reported, and so is anything past
    the media, as any component there is."""

    @staticmethod
    def _create_beats_and_shorten_the_media(
        beat_tl, tilia_state, times, beat_pattern, duration
    ) -> None:
        tilia_state.set_duration(times[-1], scale_timelines="no")
        _create_beats(beat_tl, times, beat_pattern)
        # TiLiA keeps the timeline as it is, within DURATION_JITTER_TOLERANCE.
        tilia_state.set_duration(duration, scale_timelines="keep")

    def test_a_note_on_a_last_beat_at_the_media_end_is_reported(
        self, score_tl, beat_tl, tilia_state, tmp_path
    ):
        self._create_beats_and_shorten_the_media(
            beat_tl, tilia_state, [0, 1, 2], [1], 2
        )

        success, errors = _import_with_patch(
            score_tl,
            beat_tl,
            _score_with_measures(
                _measure("".join(SCORE_ATTRIBUTES.values())),
                _measure(""),
                _measure(""),
            ),
            tmp_path,
        )

        assert success
        assert errors == ["End time '2' should be bigger than start time '2'"]
        assert _note_times(score_tl) == [(0, 1), (1, 2)]
        assert _bar_line_times(score_tl) == [1, 2, 2]

    def test_only_the_note_on_the_last_beat_is_reported(
        self, score_tl, beat_tl, tilia_state, tmp_path
    ):
        self._create_beats_and_shorten_the_media(
            beat_tl, tilia_state, [0, 1, 2, 3], [4], 3
        )

        success, errors = _import_with_patch(
            score_tl,
            beat_tl,
            _score_with_measures(
                _measure_of_quarters("".join(SCORE_ATTRIBUTES.values())),
            ),
            tmp_path,
        )

        assert success
        assert errors == ["End time '3' should be bigger than start time '3'"]
        assert _note_times(score_tl) == [(0, 1), (1, 2), (2, 3)]
        assert _bar_line_times(score_tl) == [3]

    def test_each_note_past_the_last_beat_is_reported(
        self, score_tl, beat_tl, tilia_state, tmp_path
    ):
        # Two beats tapped in a measure of four: the third and fourth quarters
        # fall on the last beat and past it.
        self._create_beats_and_shorten_the_media(
            beat_tl, tilia_state, [0.0, 1.0], [2], 1.0
        )

        success, errors = _import_with_patch(
            score_tl,
            beat_tl,
            _score_with_measures(
                _measure_of_quarters("".join(SCORE_ATTRIBUTES.values())),
            ),
            tmp_path,
        )

        assert success
        assert errors == ["End time '1.0' should be bigger than start time '1.0'"] * 2
        assert _note_times(score_tl) == [(0, 0.5), (0.5, 1)]

    def test_a_last_beat_past_the_media_end_reports_what_lies_past_it(
        self, score_tl, beat_tl, tilia_state, tmp_path
    ):
        self._create_beats_and_shorten_the_media(
            beat_tl, tilia_state, [0, 1, 2], [1], 1.5
        )

        success, errors = _import_with_patch(
            score_tl,
            beat_tl,
            _score_with_measures(
                _measure("".join(SCORE_ATTRIBUTES.values())),
                _measure(""),
                _measure(""),
            ),
            tmp_path,
        )

        assert success
        assert errors == [
            "End time '2' is bigger than media time '1.5'",
            "Time '00:02.0' is bigger than media time '00:01.5'",
            "Start time '2' is bigger than media time '1.5'",
            "Time '00:02.0' is bigger than media time '00:01.5'",
        ]
        assert _note_times(score_tl) == [(0, 1)]
        assert _bar_line_times(score_tl) == [1]

    def test_an_end_before_the_start_is_passed_over_for_the_next_end(
        self, score_tl, beat_tl, tilia_state, tmp_path
    ):
        # Fraction 0, as a segment's end, also gives where each pass of the
        # measure below ends: 1 and 2 here. The note starts at 2, so the end at 1
        # isn't its own, and only the end at 2 is reported.
        tilia_state.set_duration(10, scale_timelines="no")
        beat_tl.set_data("beat_pattern", [1])
        for time in range(4):
            beat_tl.create_beat(time)
        beat_tl.measure_numbers = [1, 1, 2, 3]
        beat_tl.recalculate_measures()

        success, errors = _import_with_patch(
            score_tl,
            beat_tl,
            _score_with_measures(
                _measure("".join(SCORE_ATTRIBUTES.values())),
                _measure("").replace(
                    "<duration>16</duration>", "<duration>0</duration>"
                ),
                _measure(""),
            ),
            tmp_path,
        )

        assert success
        assert errors == ["End time '2' should be bigger than start time '2'"]
        assert _note_times(score_tl) == [(0, 1), (1, 2), (3, 4)]

    def test_a_note_that_ends_on_the_last_beat_is_kept(
        self, score_tl, beat_tl, tilia_state, tmp_path
    ):
        self._create_beats_and_shorten_the_media(
            beat_tl, tilia_state, [0, 1, 2, 3], [2], 3
        )

        success, errors = _import_with_patch(
            score_tl,
            beat_tl,
            _score_with_measures(
                _measure_of_quarters("".join(SCORE_ATTRIBUTES.values()), notes=2),
                _measure_of_quarters("", notes=1, rests=1),
            ),
            tmp_path,
        )

        assert success
        assert errors == []
        assert _note_times(score_tl) == [(0, 1), (1, 2), (2, 3)]


@pytest.mark.parametrize(
    "time, written",
    [
        ("<time><beats>3+2</beats><beat-type>8</beat-type></time>", [("3+2", 8)]),
        (
            "<time><beats>2</beats><beat-type>4</beat-type>"
            "<beats>3</beats><beat-type>8</beat-type></time>",
            [("2", 4), ("3", 8)],
        ),
    ],
    ids=["composite", "several pairs"],
)
def test_time_signature_as_written(time, written, score_tl, beat_tl, tmp_path):
    beat_tl.beat_pattern = [4]
    for i in range(5):
        beat_tl.create_beat(i)
    beat_tl.recalculate_measures()

    success, errors = _import_with_patch(
        score_tl,
        beat_tl,
        _score_with_measures(_measure(_attributes_without("time") + time)),
        tmp_path,
    )

    assert success
    assert errors == []
    (time_signature,) = _get_components_by_kind(score_tl, ComponentKind.TIME_SIGNATURE)
    assert time_signature.get_pairs() == written


def test_time_signature_tilia_cannot_draw_is_reported(score_tl, beat_tl, tmp_path):
    beat_tl.beat_pattern = [4]
    for i in range(5):
        beat_tl.create_beat(i)
    beat_tl.recalculate_measures()
    time = "<time><beats>2.5</beats><beat-type>4</beat-type></time>"

    success, errors = _import_with_patch(
        score_tl,
        beat_tl,
        _score_with_measures(_measure(_attributes_without("time") + time)),
        tmp_path,
    )

    assert success
    assert errors == ["<time> - 2.5/4 not implemented"]
    assert not _get_components_by_kind(score_tl, ComponentKind.TIME_SIGNATURE)
