"""Undo and redo give a beat timeline back the measures they recorded.

A state's attributes are restored before its components, and the beat timeline
fits its measure lists to the beats it has when they are set. The lists are set
again once the beats are back, and as copies, since the timeline changes them
in place and the undo stack must keep them as recorded.
"""

import copy

from tests.mock import Serve
from tests.utils import undoable
from tilia.requests import Get, Post, post
from tilia.ui import commands


def _add_beats(times):
    for time in times:
        commands.execute("media.seek", time)
        commands.execute("timeline.beat.add")


def _set_measure_number(tlui, beat_index, number):
    tlui.deselect_all_elements()
    tlui.select_element(tlui[beat_index])
    with Serve(Get.FROM_USER_INT, (True, number)):
        commands.execute("timeline.beat.set_measure_number")
    tlui.deselect_all_elements()


class TestMeasuresFollowTheRestoredBeats:
    def test_undo_deleting_the_last_beat_keeps_its_measure_number(self, beat_tlui):
        _add_beats(range(5))
        _set_measure_number(beat_tlui, 4, 10)
        assert beat_tlui.timeline.measure_numbers == [1, 10]

        beat_tlui.select_element(beat_tlui[4])
        with undoable():
            commands.execute("timeline.component.delete")
        commands.execute("edit.undo")

        assert beat_tlui.timeline.measure_numbers == [1, 10]

    def test_undo_deleting_a_beat_keeps_a_measure_shorter_than_the_pattern(
        self, beat_tlui, tls
    ):
        timeline = beat_tlui.timeline
        timeline.beat_pattern = [1]
        _add_beats(range(6))
        tls.set_timeline_data(timeline.id, "beat_pattern", [4])
        beat_tlui.deselect_all_elements()
        post(Post.APP_STATE_RECORD, "beat pattern")

        beat_tlui.select_element(beat_tlui[1])
        with undoable():
            commands.execute("timeline.component.delete")
        commands.execute("edit.undo")

        assert timeline.beats_in_measure == [1, 1, 1, 1, 1, 1]

    def test_undo_deleting_all_beats_keeps_a_measure_length_set_by_hand(
        self, beat_tlui
    ):
        timeline = beat_tlui.timeline
        _add_beats(range(6))
        timeline.set_beat_amount_in_measure(0, 2)
        post(Post.APP_STATE_RECORD, "set beat amount")
        assert timeline.beats_in_measure == [2, 4]

        beat_tlui.select_all_elements()
        with undoable():
            commands.execute("timeline.component.delete")
        commands.execute("edit.undo")

        assert timeline.beats_in_measure == [2, 4]


class TestTheUndoStackKeepsItsStates:
    def test_undo_leaves_the_state_it_restores_as_recorded(
        self, beat_tlui, tilia_state
    ):
        recorded = tilia_state.undo_manager.stack[-1]["state"]
        as_recorded = copy.deepcopy(recorded)

        _add_beats([0])
        commands.execute("edit.undo")

        assert recorded == as_recorded

    def test_an_edit_after_an_undo_leaves_the_restored_state_as_recorded(
        self, beat_tlui, tls
    ):
        timeline = beat_tlui.timeline
        _add_beats([0])
        commands.execute("edit.undo")
        tls.set_timeline_data(timeline.id, "beat_pattern", [3])
        post(Post.APP_STATE_RECORD, "beat pattern")
        commands.execute("edit.undo")

        assert timeline.measure_numbers == []

    def test_undo_after_edits_that_follow_a_redo(self, beat_tlui, tilia_errors):
        beat_tlui.timeline.beat_pattern = [1]
        _add_beats([0, 1])
        commands.execute("edit.undo")
        commands.execute("edit.redo")
        # Each beat adds a measure; the state the redo restored must not get it.
        _add_beats([2, 3])
        commands.execute("edit.undo")
        commands.execute("edit.undo")

        tilia_errors.assert_no_error()
        assert beat_tlui.timeline.beats_in_measure == [1, 1]
        assert beat_tlui.timeline.measure_numbers == [1, 2]
