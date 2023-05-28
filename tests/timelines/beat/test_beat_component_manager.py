import functools
import itertools
import logging
from unittest.mock import MagicMock, patch

import pytest
import logging

from tilia.events import Event
from tilia.exceptions import CreateComponentError
from tilia.timelines.beat.timeline import BeatTLComponentManager
from tilia.timelines.component_kinds import ComponentKind

logger = logging.getLogger(__name__)


@pytest.fixture
def cm():
    timeline = MagicMock()
    timeline.get_media_length.return_value = 100
    timeline.beat_pattern = [2]
    timeline.beats_in_measure = []
    _cm = BeatTLComponentManager()

    def create_component(*args, **kwargs):
        return BeatTLComponentManager.create_component(
            _cm, ComponentKind.BEAT, timeline, *args, **kwargs
        )

    _cm.create_component = create_component
    _cm.timeline = timeline
    yield _cm
    del _cm._components
    del _cm.id_to_component


class DummyBeat:
    id_counter = itertools.count()

    def __init__(self, time):
        self.id = next(self.id_counter)
        self.time = time

    def __str__(self):
        return f"DummyBeat({self.time})"


# noinspection PyAttributeOutsideInit
class DummyUI:
    def update_drawing_as_first_in_measure(self, value):
        self.first_in_measure = value


class TestBeatTlComponentManager:
    def test_create_overlapping_beat_raises_error(self, cm):
        cm.create_component(time=1)
        with pytest.raises(CreateComponentError):
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
        with patch(
            "tilia.timelines.beat.timeline.BeatTLComponentManager.post_component_event"
        ) as post_mock:
            cm.update_beat_uis()

        expected_first_in_measure = [False, True, False, True, True]
        expected_labels = ["", "a", "", "b", "c"]

        for i, beat in enumerate(cm._components):
            post_mock.assert_any_call(
                Event.BEAT_UPDATED,
                beat.id,
                expected_first_in_measure[i],
                expected_labels[i],
            )

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
        with patch(
            "tilia.timelines.beat.timeline.BeatTLComponentManager.post_component_event"
        ) as post_mock:
            cm.update_beat_uis()

        expected_first_in_measure = [True, False, True, False, True]
        expected_labels = ["a", "", "b", "", "c"]

        for i, beat in enumerate(cm._components):
            post_mock.assert_any_call(
                Event.BEAT_UPDATED,
                beat.id,
                expected_first_in_measure[i],
                expected_labels[i],
            )

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
