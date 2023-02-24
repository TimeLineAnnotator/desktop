import functools
import logging
from unittest.mock import MagicMock, patch

import pytest
import logging

from tilia.timelines.beat.timeline import BeatTLComponentManager
from tilia.timelines.component_kinds import ComponentKind

logger = logging.getLogger(__name__)


@pytest.fixture
def cm():
    timeline = MagicMock()
    timeline.beat_pattern = [2]
    timeline.beats_in_measure = []
    _cm = BeatTLComponentManager()
    _cm.create_component = functools.partial(
        _cm.create_component, timeline=timeline, kind=ComponentKind.BEAT
    )
    _cm.timeline = MagicMock()
    yield _cm
    _cm.clear()


class DummyBeat:
    def __init__(self, time):
        self.time = time
        self.ui = DummyBeatUI()

    def __str__(self):
        return f"DummyBeat({self.time})"


class DummyBeatUI:
    def __init__(self):
        self.first_in_measure = False
        self.label = ""
        self.update_position = MagicMock()

    def update_drawing_as_first_in_measure(self, value):
        self.first_in_measure = value


# noinspection PyAttributeOutsideInit
class DummyUI:
    def update_drawing_as_first_in_measure(self, value):
        self.first_in_measure = value


class TestBeatTlComponentManager:
    def test_create_overlapping_beat_raises_error(self, cm):
        cm.create_component(time=1)
        with pytest.raises(ValueError):
            with patch("tkinter.messagebox.showerror", lambda *args, **kwargs: None):
                cm.create_component(time=1)

    def test_update_beat_uis_1(self, cm):
        cm.timeline.measure_numbers = ["a", "b", "c"]
        measure_index_map = {0: 0, 1: 0, 2: 0, 3: 1, 4: 2}
        cm.timeline.get_measure_index = lambda i: measure_index_map[i]
        cm._components = [
            DummyBeat(1),
            DummyBeat(2),
            DummyBeat(3),
            DummyBeat(4),
            DummyBeat(5),
        ]
        cm.timeline.beats_that_start_measures = [1, 3, 4]
        cm.update_beat_uis()

        expected_first_in_measure = [False, True, False, True, True]
        expected_labels = ["", "a", "", "b", "c"]

        for i, beat in enumerate(cm._components):
            assert beat.ui.first_in_measure == expected_first_in_measure[i]
            assert beat.ui.label == expected_labels[i]

    def test_update_beat_uis_2(self, cm):
        cm.timeline.measure_numbers = ["a", "b", "c"]
        measure_index_map = {0: 0, 1: 0, 2: 1, 3: 1, 4: 2}
        cm.timeline.get_measure_index = lambda i: measure_index_map[i]
        cm._components = [
            DummyBeat(1),
            DummyBeat(2),
            DummyBeat(3),
            DummyBeat(4),
            DummyBeat(5),
        ]
        cm.timeline.beats_that_start_measures = [0, 2, 4]
        cm.update_beat_uis()

        expected_first_in_measure = [True, False, True, False, True]
        expected_labels = ["a", "", "b", "", "c"]

        for i, beat in enumerate(cm._components):
            assert beat.ui.first_in_measure == expected_first_in_measure[i]
            assert beat.ui.label == expected_labels[i]

    def test_distribute_beats_2beats(self, cm):
        cm.timeline.beats_that_start_measures = [0, 2, 4]
        cm.timeline.get_beat_index = lambda b: cm.ordered_beats.index(b)
        cm._components = [
            DummyBeat(1),
            DummyBeat(2),
            DummyBeat(3),
            DummyBeat(3.1),
            DummyBeat(5),
            DummyBeat(6),
        ]

        cm.distribute_beats(1)

        assert cm._components[2].time == 3
        assert cm._components[3].time == 4

    def test_distribute_beats_3beats(self, cm):
        cm.timeline.beats_that_start_measures = [0, 3, 6]
        cm.timeline.get_beat_index = lambda b: cm.ordered_beats.index(b)
        cm._components = [
            DummyBeat(1),
            DummyBeat(2),
            DummyBeat(3),
            DummyBeat(4),
            DummyBeat(4.1),
            DummyBeat(4.2),
            DummyBeat(7),
            DummyBeat(8),
            DummyBeat(9),
        ]

        cm.distribute_beats(1)

        assert cm._components[3].time == 4
        assert cm._components[4].time == 5
        assert cm._components[5].time == 6

    def test_distribute_beats_last_measure_raises_error(self, cm):
        cm.timeline.measure_count = 2

        with pytest.raises(ValueError):
            with patch("tkinter.messagebox.showerror", lambda *args, **kwargs: None):
                cm.distribute_beats(1)
