"""Clearing a beat timeline leaves no measures behind, as deleting its beats
doesn't."""

from tests.mock import Serve
from tests.utils import undoable
from tilia.requests import Get
from tilia.ui import commands


def _add_beats(times):
    for time in times:
        commands.execute("media.seek", time)
        commands.execute("timeline.beat.add")


def _clear(tlui):
    with Serve(Get.FROM_USER_YES_OR_NO, True):
        commands.execute("timeline.clear", tlui)


def _number_first_measure(tlui, number):
    tlui.select_element(tlui[0])
    with Serve(Get.FROM_USER_INT, (True, number)):
        commands.execute("timeline.beat.set_measure_number")
    tlui.deselect_all_elements()


def test_clear_leaves_no_measures(beat_tlui):
    timeline = beat_tlui.timeline
    _add_beats(range(5))
    _number_first_measure(beat_tlui, 5)
    assert timeline.measure_numbers == [5, 6]

    _clear(beat_tlui)

    assert timeline.beats_in_measure == []
    assert timeline.measure_numbers == []
    assert timeline.measures_to_force_display == []


def test_a_beat_added_after_clear_is_in_measure_one(beat_tlui):
    _add_beats(range(5))
    _number_first_measure(beat_tlui, 5)
    _clear(beat_tlui)

    _add_beats([0])

    assert beat_tlui.timeline[0].metric_position.measure == 1


def test_redo_clear_gives_the_state_recorded(beat_tlui):
    # Measures that follow the beat pattern, as undoing the deletion of beats
    # restores those of another kind wrongly (see TimeLineAnnotator/desktop#889).
    _add_beats(range(5))

    with undoable():
        _clear(beat_tlui)
