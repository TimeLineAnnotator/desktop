import pytest
import logging
from unittest.mock import MagicMock

from tilia.exceptions import InvalidComponentKindError
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.marker.timeline import (
    MarkerTLComponentManager,
    MarkerTimeline,
)
from tilia.timelines.serialize import serialize_component, _deserialize_component
from tilia.timelines.timeline_kinds import TimelineKind

logger = logging.getLogger(__name__)


class TestMarkerTimeline:
    # TEST CREATE
    def test_create_marker(self, marker_tl):
        marker_tl.create_marker(time=0)

        assert len(marker_tl.markers) == 1

    # TEST DELETE
    def test_delete_marker(self, marker_tl):
        mrk1 = marker_tl.create_marker(time=0)

        marker_tl.on_request_to_delete_components([mrk1])

        assert not marker_tl.markers

    # TEST SERIALIZE
    def test_serialize_unit(self, marker_tl):
        unit_kwargs = {
            "time": 0,
            "color": "#000000",
            "comments": "my comments",
            "label": "my label",
        }

        mrk1 = marker_tl.create_marker(**unit_kwargs)

        # noinspection PyTypeChecker
        srlz_mrk1 = serialize_component(mrk1)

        for key, value in unit_kwargs.items():
            assert srlz_mrk1[key] == value

    def test_deserialize_unit(self, marker_tl):
        unit_kwargs = {
            "time": 0,
            "comments": "my comments",
            "color": "#000000",
            "label": "my label",
        }

        mrk1 = marker_tl.create_marker(**unit_kwargs)

        # noinspection PyTypeChecker
        serialized_mrk1 = serialize_component(mrk1)

        deserialized_mrk1 = _deserialize_component(marker_tl, serialized_mrk1)

        for attr in unit_kwargs:
            assert getattr(mrk1, attr) == getattr(deserialized_mrk1, attr)

    def test_serialize_timeline(self, marker_tl):
        marker_tl.create_marker(time=0)

        serialized_timeline = marker_tl.get_state()

        assert serialized_timeline["height"] == MarkerTimeline.DEFAULT_HEIGHT
        assert serialized_timeline["is_visible"] is True
        assert serialized_timeline["kind"] == TimelineKind.MARKER_TIMELINE.name
        assert len(serialized_timeline["components"]) == 1

    # TEST UNDO
    def test_restore_state(self, marker_tl):
        marker_tl.create_marker(time=0)
        marker_tl.create_marker(time=1)

        state = marker_tl.get_state()

        marker_tl.clear()

        assert len(marker_tl.markers) == 0

        marker_tl.restore_state(state)

        assert len(marker_tl.markers) == 2

    # TEST RIGHT CLICK OPTIONS


class TestMarkerTimelineComponentManager:
    # TEST CREATE COMPONENT
    def test_create_component(self, marker_tl):
        assert marker_tl.create_marker(0)
        component_manager = MarkerTLComponentManager()
        timeline = MagicMock()
        timeline.get_media_length = lambda: 100
        component_manager.timeline = timeline
        hunit = component_manager.create_component(
            ComponentKind.MARKER, timeline=MagicMock(), time=0
        )
        assert hunit

        with pytest.raises(InvalidComponentKindError):
            # noinspection PyTypeChecker
            component_manager.create_component("INVALID KIND", time=0)

    # TEST CLEAR
    def test_clear(self, marker_tl):
        marker_tl.create_marker(time=0)
        marker_tl.create_marker(time=0)
        marker_tl.create_marker(time=0)

        marker_tl.component_manager.clear()

        assert not marker_tl.component_manager._components

    # TEST SERIALIZE
    # noinspection PyUnresolvedReferences
    def test_serialize_components(self, marker_tl):
        mrk1 = marker_tl.create_marker(time=0)
        mrk2 = marker_tl.create_marker(time=1)
        mrk3 = marker_tl.create_marker(time=2)

        serialized_components = marker_tl.component_manager.serialize_components()

        for unit in [mrk1, mrk2, mrk3]:
            assert serialized_components[unit.id]["time"] == unit.time

    # noinspection PyUnresolvedReferences
    def test_deserialize_components(self, marker_tl):
        mrk1 = marker_tl.create_marker(time=0)
        mrk2 = marker_tl.create_marker(time=1)
        mrk3 = marker_tl.create_marker(time=2)

        serialized_components = marker_tl.component_manager.serialize_components()

        marker_tl.component_manager.clear()

        marker_tl.component_manager.deserialize_components(serialized_components)

        assert len(marker_tl.markers) == 3
        assert {
            dsr_mrk.time for dsr_mrk in marker_tl.component_manager._components
        } == {u.time for u in [mrk1, mrk2, mrk3]}
