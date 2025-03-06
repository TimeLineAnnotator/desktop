from tests.mock import Serve
from tests.constants import EXAMPLE_MUSICXML_PATH
from tilia.parsers.score.musicxml import notes_from_musicXML
from tilia.requests import Get
from tilia.timelines.component_kinds import ComponentKind


class TestInsertMeasureZero:
    def setup_valid_beats(self, beat_tl):
        beat_tl.beat_pattern = [3]

        for i in range(5, 12):
            beat_tl.create_beat(i)

        beat_tl.recalculate_measures()

    def test_user_accpets(self, qtui, score_tlui, beat_tl, tmp_path, tilia_state):
        self.setup_valid_beats(beat_tl)

        with Serve(Get.FROM_USER_YES_OR_NO, True):
            notes_from_musicXML(score_tlui.timeline, beat_tl, EXAMPLE_MUSICXML_PATH)

        clefs = score_tlui.timeline.get_components_by_attr("KIND", ComponentKind.CLEF)
        assert len(clefs) == 1

        notes = score_tlui.timeline.get_components_by_attr("KIND", ComponentKind.NOTE)
        assert len(notes) == 4

        time_signatures = score_tlui.timeline.get_components_by_attr(
            "KIND", ComponentKind.TIME_SIGNATURE
        )
        assert len(time_signatures) == 1

        assert beat_tl.measure_numbers[0] == 0
        assert beat_tl._beats_in_measure[0] == 1

    def test_user_accepts_but_no_space_for_measure(
        self, qtui, score_tlui, beat_tl, tmp_path, tilia_state
    ):
        beat_tl.fill_with_beats(beat_tl.FillMethod.BY_AMOUNT, 10)

        with Serve(Get.FROM_USER_YES_OR_NO, True):
            notes_from_musicXML(score_tlui.timeline, beat_tl, EXAMPLE_MUSICXML_PATH)

        assert len(score_tlui) == 0

    def test_user_accepts_but_less_than_two_measure_in_beat_timeline(
        self, qtui, score_tlui, beat_tl, tmp_path, tilia_state
    ):
        beat_tl.beat_pattern = [2]
        beat_tl.create_beat(5)
        beat_tl.create_beat(6)
        beat_tl.recalculate_measures()

        with Serve(Get.FROM_USER_YES_OR_NO, True):
            notes_from_musicXML(score_tlui.timeline, beat_tl, EXAMPLE_MUSICXML_PATH)

        assert len(score_tlui) == 0

    def test_no_beat_1(self, qtui, score_tlui, beat_tl, tmp_path, tilia_state):
        self.setup_valid_beats(beat_tl)

        beat_tl.set_measure_number(0, 2)

        notes_from_musicXML(score_tlui.timeline, beat_tl, EXAMPLE_MUSICXML_PATH)

        # no prompt for measure 0 as there is no measure 1
        # and measure 2 should have been imported
        notes = score_tlui.timeline.get_components_by_attr("KIND", ComponentKind.NOTE)
        assert len(notes) == 1
