import pytest

from unittest.mock import MagicMock, ANY, patch
import itertools
import logging

from tilia.events import unsubscribe_from_all
from tilia.timelines.collection import TimelineCollection
from tilia.timelines.common import InvalidComponentKindError
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.marker.timeline import (
    MarkerTLComponentManager,
    MarkerTimeline,
)

# noinspection PyProtectedMember
from tilia.timelines.serialize import serialize_component, _deserialize_component
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.timeline import TimelineUIElementManager
from tilia.ui.timelines.marker import MarkerTimelineUI, MarkerUI

logger = logging.getLogger(__name__)


@pytest.fixture
def tl_with_ui() -> MarkerTimeline:
    id_counter = itertools.count()

    tl_coll_mock = MagicMock()
    tl_coll_mock.get_id = lambda: next(id_counter)

    tlui_coll_mock = MagicMock()
    tlui_coll_mock.get_id = lambda: next(id_counter)

    component_manager = MarkerTLComponentManager()
    timeline = MarkerTimeline(tl_coll_mock, component_manager)

    timeline.ui = MarkerTimelineUI(
        timeline_ui_collection=tlui_coll_mock,
        element_manager=TimelineUIElementManager(
            MarkerTimelineUI.ELEMENT_KINDS_TO_ELEMENT_CLASSES
        ),
        canvas=MagicMock(),
        toolbar=MagicMock(),
        name="",
    )
    component_manager.associate_to_timeline(timeline)
    yield timeline
    unsubscribe_from_all(timeline)
    unsubscribe_from_all(timeline.ui)


class TestMarkerTimeline:

    # TEST CREATE
    def test_create_marker(self, tl_with_ui):
        tl_with_ui.create_timeline_component(ComponentKind.MARKER, time=0)

        assert len(tl_with_ui.component_manager._components) == 1

    # TEST DELETE
    def test_delete_marker(self, mrk_tl):
        mrk1 = mrk_tl.create_timeline_component(ComponentKind.MARKER, time=0)

        mrk_tl.on_request_to_delete_components([mrk1])

        assert not mrk_tl.component_manager._components

    # TEST SERIALIZE
    def test_serialize_unit(self, tl_with_ui):
        unit_kwargs = {
            "time": 0,
            "color": "#000000",
            "comments": "my comments",
            "label": "my label",
        }

        mrk1 = tl_with_ui.create_timeline_component(ComponentKind.MARKER, **unit_kwargs)

        # noinspection PyTypeChecker
        srlz_mrk1 = serialize_component(mrk1)

        for key, value in unit_kwargs.items():
            assert srlz_mrk1[key] == value

    def test_deserialize_unit(self, tl_with_ui):
        unit_kwargs = {"time": 0, "comments": "my comments"}

        mrk1 = tl_with_ui.create_timeline_component(ComponentKind.MARKER, **unit_kwargs)

        # noinspection PyTypeChecker
        serialized_mrk1 = serialize_component(mrk1)

        deserialized_mrk1 = _deserialize_component(tl_with_ui, serialized_mrk1)

        for attr in unit_kwargs:
            assert getattr(mrk1, attr) == getattr(deserialized_mrk1, attr)

    def test_deserialize_unit_with_serializable_by_ui_attributes(self, tl_with_ui):
        serializable_by_ui_attrs = {"color": "#000000", "label": "my label"}

        mrk1 = tl_with_ui.create_timeline_component(ComponentKind.MARKER, time=0)

        # noinspection PyTypeChecker
        serialized_mrk1 = serialize_component(mrk1)

        deserialized_mrk1 = _deserialize_component(tl_with_ui, serialized_mrk1)

        for attr in serializable_by_ui_attrs:
            assert getattr(mrk1.ui, attr) == getattr(deserialized_mrk1.ui, attr)

    def test_serialize_timeline(self, tl_with_ui):
        _ = tl_with_ui.create_timeline_component(ComponentKind.MARKER, time=0)

        serialized_timeline = tl_with_ui.get_state()

        assert serialized_timeline["height"] == MarkerTimelineUI.DEFAULT_HEIGHT
        assert serialized_timeline["is_visible"] is True
        assert serialized_timeline["kind"] == TimelineKind.MARKER_TIMELINE.name
        assert len(serialized_timeline["components"]) == 1

    # TEST UNDO
    def test_restore_state(self, tl_with_ui):
        mrk1 = tl_with_ui.create_timeline_component(ComponentKind.MARKER, time=0)
        mrk2 = tl_with_ui.create_timeline_component(ComponentKind.MARKER, time=1)

        state = tl_with_ui.get_state()

        tl_with_ui.clear()

        assert len(tl_with_ui.component_manager._components) == 0

        tl_with_ui.restore_state(state)

        assert len(tl_with_ui.component_manager._components) == 2

    # TEST RIGHT CLICK OPTIONS
    @patch("tilia.ui.common.ask_for_color")
    def test_right_click_change_color(self, ask_for_color_mock, tl_with_ui):

        ask_for_color_mock.return_value = "#000000"

        mrk1 = tl_with_ui.create_timeline_component(ComponentKind.MARKER, time=0)

        tl_with_ui.ui.right_clicked_element = mrk1.ui

        tl_with_ui.ui.right_click_menu_change_color()

        assert mrk1.ui.color == "#000000"

    @patch("tilia.ui.common.ask_for_color")
    def test_right_click_reset_color(self, ask_for_color_mock, tl_with_ui):

        ask_for_color_mock.return_value = "#000000"

        mrk1 = tl_with_ui.create_timeline_component(ComponentKind.MARKER, time=0)

        tl_with_ui.ui.right_clicked_element = mrk1.ui

        tl_with_ui.ui.right_click_menu_change_color()
        tl_with_ui.ui.right_click_menu_reset_color()

        assert mrk1.ui.color == MarkerUI.DEFAULT_COLOR


class TestMarkerTimelineComponentManager:

    # TEST CREATE COMPONENT
    def test_create_component(self):
        component_manager = MarkerTLComponentManager()
        hunit = component_manager.create_component(
            ComponentKind.MARKER, timeline=MagicMock(), time=0
        )
        assert hunit

        with pytest.raises(InvalidComponentKindError):
            # noinspection PyTypeChecker
            component_manager.create_component("INVALID KIND", time=0)

    # TEST CLEAR
    def test_clear(self, mrk_tl):
        _ = mrk_tl.create_timeline_component(ComponentKind.MARKER, time=0)
        _ = mrk_tl.create_timeline_component(ComponentKind.MARKER, time=0)
        _ = mrk_tl.create_timeline_component(ComponentKind.MARKER, time=0)

        mrk_tl.component_manager.clear()

        assert not mrk_tl.component_manager._components

    # TEST SERIALIZE
    # noinspection PyUnresolvedReferences
    def test_serialize_components(self, tl_with_ui):
        mrk1 = tl_with_ui.create_timeline_component(ComponentKind.MARKER, time=0)
        mrk2 = tl_with_ui.create_timeline_component(ComponentKind.MARKER, time=1)
        mrk3 = tl_with_ui.create_timeline_component(ComponentKind.MARKER, time=2)

        serialized_components = tl_with_ui.component_manager.serialize_components()

        for unit in [mrk1, mrk2, mrk3]:
            assert serialized_components[unit.id]["time"] == unit.time

    # noinspection PyUnresolvedReferences
    def test_deserialize_components(self, tl_with_ui):
        mrk1 = tl_with_ui.create_timeline_component(ComponentKind.MARKER, time=0)
        mrk2 = tl_with_ui.create_timeline_component(ComponentKind.MARKER, time=1)
        mrk3 = tl_with_ui.create_timeline_component(ComponentKind.MARKER, time=2)

        serialized_components = tl_with_ui.component_manager.serialize_components()

        tl_with_ui.component_manager.clear()

        tl_with_ui.component_manager.deserialize_components(serialized_components)

        assert len(tl_with_ui.component_manager._components) == 3
        assert {
            dsr_mrk.time for dsr_mrk in tl_with_ui.component_manager._components
        } == {u.time for u in [mrk1, mrk2, mrk3]}
