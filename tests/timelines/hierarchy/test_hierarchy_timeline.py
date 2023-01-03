import pytest

from unittest.mock import MagicMock, ANY, patch
import itertools
import logging

from tilia.events import Event
from tilia.timelines.collection import TimelineCollection
from tilia.timelines.common import InvalidComponentKindError
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.hierarchy.components import HierarchyOperationError
from tilia.timelines.hierarchy.timeline import (
    HierarchyTLComponentManager,
    HierarchyTimeline,
)
from tilia.timelines.hierarchy.common import ParentChildRelation

# noinspection PyProtectedMember
from tilia.timelines.serialize import serialize_component, _deserialize_component
from tilia.timelines.state_actions import StateAction
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.timeline import TimelineUIElementManager
from tilia.ui.timelines.hierarchy import HierarchyTimelineUI

logger = logging.getLogger(__name__)


@pytest.fixture
def tl_with_ui() -> HierarchyTimeline:
    id_counter = itertools.count()

    tl_coll_mock = MagicMock()
    tl_coll_mock.get_id = lambda: next(id_counter)

    tlui_coll_mock = MagicMock()
    tlui_coll_mock.get_id = lambda: next(id_counter)

    component_manager = HierarchyTLComponentManager()
    timeline = HierarchyTimeline(tl_coll_mock, component_manager)

    ui = HierarchyTimelineUI(
        timeline_ui_collection=tlui_coll_mock,
        element_manager=TimelineUIElementManager(
            HierarchyTimelineUI.ELEMENT_KINDS_TO_ELEMENT_CLASSES
        ),
        canvas=MagicMock(),
        toolbar=MagicMock(),
        name="",
    )
    timeline.ui = ui
    ui.timeline = timeline

    component_manager.associate_to_timeline(timeline)
    yield timeline


@pytest.fixture
def tl() -> HierarchyTimeline:
    component_manager = HierarchyTLComponentManager()
    timeline = HierarchyTimeline(MagicMock(), component_manager)

    timeline.ui = MagicMock()
    component_manager.associate_to_timeline(timeline)
    yield timeline


class TestHierarchyTimeline:

    # TEST CREATE
    def test_create_hierarchy(self):
        tl_coll = TimelineCollection(MagicMock())
        component_manager = HierarchyTLComponentManager()
        tl = HierarchyTimeline(tl_coll, component_manager)
        tl.ui = MagicMock()
        tl.create_timeline_component(ComponentKind.HIERARCHY, start=0, end=1, level=1)

        tl.ui.get_ui_for_component.assert_called_with(
            ComponentKind.HIERARCHY, ANY, start=0, end=1, level=1
        )

        assert len(tl.component_manager._components) == 1

    # TEST DELETE
    def test_delete_hierarchy(self, tl):
        hrc1 = tl.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 1)

        tl.on_request_to_delete_components([hrc1])

        assert not tl.component_manager._components

    # TEST RIGHT CLICK OPTIONS
    @patch("tilia.ui.common.ask_for_color")
    def test_right_click_change_color(self, ask_for_color_mock, tl_with_ui):

        ask_for_color_mock.return_value = "#000000"

        hrc1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0, 1)

        tl_with_ui.ui.right_clicked_element = hrc1.ui

        tl_with_ui.ui.right_click_menu_change_color()

        assert hrc1.ui.color == "#000000"

    @patch("tilia.ui.common.ask_for_color")
    def test_right_click_reset_color(self, ask_for_color_mock, tl_with_ui):

        ask_for_color_mock.return_value = "#000000"

        hrc1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0, 1)

        tl_with_ui.ui.right_clicked_element = hrc1.ui

        tl_with_ui.ui.right_click_menu_change_color()
        tl_with_ui.ui.right_click_menu_reset_color()

        assert hrc1.ui.color == hrc1.ui.get_default_level_color(hrc1.level)

    def test_right_click_increase_level(self, tl_with_ui):

        hrc1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0, 1)

        tl_with_ui.ui.right_clicked_element = hrc1.ui

        tl_with_ui.ui.right_click_menu_increase_level()

        assert hrc1.level == 2

    def test_right_click_decrease_level(self, tl_with_ui):

        hrc1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0, 2)

        tl_with_ui.ui.right_clicked_element = hrc1.ui

        tl_with_ui.ui.right_click_menu_decrease_level()

        assert hrc1.level == 1

    # TEST SERIALIZE
    def test_serialize_unit(self, tl_with_ui):
        unit_kwargs = {
            "start": 0,
            "end": 1,
            "level": 1,
            "color": "#000000",
            "comments": "my comments",
            "label": "my label",
            "formal_type": "my formal type",
            "formal_function": "my formal function",
        }

        hrc1 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, **unit_kwargs
        )

        # noinspection PyTypeChecker
        srlz_hrc1 = serialize_component(hrc1)

        for key, value in unit_kwargs.items():
            assert srlz_hrc1[key] == value

        assert srlz_hrc1["parent"] is None
        assert srlz_hrc1["children"] == []

    def test_serialize_unit_with_parent(self, tl):

        hrc1 = tl.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 1)

        hrc2 = tl.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 2)

        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc2, children=[hrc1])
        )
        # noinspection PyTypeChecker
        srlz_hrc1 = serialize_component(hrc1)

        assert srlz_hrc1["parent"] == hrc2.id

    def test_serialize_unit_with_children(self, tl):

        hrc1 = tl.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 1)

        hrc2 = tl.create_timeline_component(ComponentKind.HIERARCHY, 0.5, 1, 1)

        hrc3 = tl.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 2)

        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc3, children=[hrc1, hrc2])
        )
        # noinspection PyTypeChecker
        srlz_hrc3 = serialize_component(hrc3)

        assert set(srlz_hrc3["children"]) == {hrc1.id, hrc2.id}

    def test_deserialize_unit(self, tl_with_ui):
        unit_kwargs = {
            "start": 0,
            "end": 1,
            "level": 1,
            "comments": "my comments",
            "formal_type": "my formal type",
            "formal_function": "my formal function",
        }

        hrc1 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, **unit_kwargs
        )

        # noinspection PyTypeChecker
        serialized_hrc1 = serialize_component(hrc1)

        deserialized_hrc1 = _deserialize_component(tl_with_ui, serialized_hrc1)

        for attr in unit_kwargs:
            assert getattr(hrc1, attr) == getattr(deserialized_hrc1, attr)

    def test_deserialize_unit_with_serializable_by_ui_attributes(self, tl_with_ui):
        serializable_by_ui_attrs = {"color": "#000000", "label": "my label"}

        hrc1 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, 0, 1, 1, **serializable_by_ui_attrs
        )

        # noinspection PyTypeChecker
        serialized_hrc1 = serialize_component(hrc1)

        deserialized_hrc1 = _deserialize_component(tl_with_ui, serialized_hrc1)

        for attr in serializable_by_ui_attrs:
            assert getattr(hrc1.ui, attr) == getattr(deserialized_hrc1.ui, attr)

    # noinspection PyTypeChecker, PyUnresolvedReferences
    @patch(
        "tilia.timelines.hierarchy.timeline.HierarchyTimeline.update_ui_with_parent_child_relation"
    )
    def test_deserialize_unit_with_parent(
        self, update_ui_parent_child_mock, tl_with_ui
    ):

        hrc1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 1)

        hrc2 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 2)

        tl_with_ui.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc2, children=[hrc1])
        )

        serialized_hrc1 = serialize_component(hrc1)

        update_ui_parent_child_mock.return_value = None

        deserialized_hrc1 = _deserialize_component(tl_with_ui, serialized_hrc1)

        assert deserialized_hrc1.parent == hrc2.id

    # noinspection PyTypeChecker, PyUnresolvedReferences
    @patch(
        "tilia.timelines.hierarchy.timeline.HierarchyTimeline.update_ui_with_parent_child_relation"
    )
    def test_deserialize_unit_with_children(
        self, update_ui_parent_child_mock, tl_with_ui
    ):

        hrc1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 1)

        hrc2 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0.5, 1, 1)

        hrc3 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 2)

        tl_with_ui.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc3, children=[hrc1, hrc2])
        )

        serialized_hrc3 = serialize_component(hrc3)

        update_ui_parent_child_mock.return_value = None

        deserialized_hrc3 = _deserialize_component(tl_with_ui, serialized_hrc3)

        assert deserialized_hrc3.children == [hrc1.id, hrc2.id]

    def test_serialize_timeline(self, tl_with_ui):
        _ = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 1)

        serialized_timeline = tl_with_ui.get_state()

        assert serialized_timeline["height"] == HierarchyTimelineUI.DEFAULT_HEIGHT
        assert serialized_timeline["is_visible"] is True
        assert serialized_timeline["kind"] == TimelineKind.HIERARCHY_TIMELINE.name
        assert len(serialized_timeline["components"])

    # TEST UNDO
    def test_restore_state(self, tl_with_ui):
        hrc1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 1)
        hrc2 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 1, 2, 1)

        state = tl_with_ui.get_state()

        tl_with_ui.on_request_to_delete_components([hrc1])
        tl_with_ui.on_request_to_delete_components([hrc2])

        assert len(tl_with_ui.component_manager._components) == 0

        tl_with_ui.restore_state(state)

        assert len(tl_with_ui.component_manager._components) == 2


class TestHierarchyTimelineComponentManager:

    # TEST CREATE COMPONENT
    def test_create_component(self):
        component_manager = HierarchyTLComponentManager()
        hunit = component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=MagicMock(), start=0, end=0, level=1
        )
        assert hunit

        with pytest.raises(InvalidComponentKindError):
            # noinspection PyTypeChecker
            component_manager.create_component("INVALID KIND", start=0, end=0, level=1)

    def test_create_unit_below(self):
        component_manager = HierarchyTLComponentManager()
        component_manager.timeline = MagicMock()
        parent = component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=MagicMock(), start=0, end=0, level=3
        )
        child = component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=MagicMock(), start=0, end=0, level=1
        )

        component_manager._make_parent_child_relation(
            ParentChildRelation(parent=parent, children=[child])
        )

        component_manager.create_unit_below(parent)

        assert parent.children[0] == child.parent

    # TEST CLEAR
    def test_clear(self, tl):
        _ = tl.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.0, end=0.1, level=1
        )
        _ = tl.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.1, end=0.2, level=2
        )
        _ = tl.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.2, end=0.3, level=3
        )

        tl.component_manager.clear()

        assert not tl.component_manager._components

    # TEST GROUP
    def test_group_two_units(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0, end=0.1, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )

        tl.component_manager.group([hrc1, hrc2])

        assert hrc1.parent == hrc2.parent
        assert hrc1.parent.level == 2

    def test_group_two_units_out_of_order(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0, end=0.1, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )

        tl.component_manager.group([hrc2, hrc1])

        assert hrc1.parent == hrc2.parent

    def test_group_two_units_with_units_of_same_level_in_between(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0, end=0.1, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=1
        )
        hrc4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.3, end=0.4, level=1
        )

        tl.component_manager.group([hrc1, hrc4])

        assert hrc1.parent == hrc2.parent == hrc3.parent == hrc4.parent

    def test_group_two_units_with_units_of_different_level_in_between(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0, end=0.1, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=2
        )
        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=3
        )
        hrc4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.3, end=0.4, level=1
        )

        tl.component_manager.group([hrc1, hrc4])

        assert hrc1.parent == hrc2.parent == hrc3.parent == hrc4.parent
        assert hrc1.parent.level == 4

    def test_group_two_units_with_unit_with_children_in_between(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0, end=0.1, level=2
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=1
        )
        hrc4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.3, level=2
        )
        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc4, children=[hrc2, hrc3])
        )
        hrc5 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.3, end=0.4, level=2
        )

        tl.component_manager.group([hrc1, hrc5])

        assert hrc1.parent == hrc4.parent == hrc5.parent

    def test_group_three_units_with_units_between_grouped_units(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0, end=0.1, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=1
        )
        hrc4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.3, end=0.4, level=1
        )
        hrc5 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.4, end=0.5, level=1
        )

        tl.component_manager.group([hrc1, hrc3, hrc5])

        assert hrc1.parent == hrc2.parent == hrc3.parent == hrc4.parent

    def test_group_one_unit_raises_error(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0, end=0.1, level=1
        )
        with pytest.raises(HierarchyOperationError):
            tl.component_manager.group([hrc1])

    def test_group_empty_list_raises_error(self, tl):
        with pytest.raises(HierarchyOperationError):
            tl.component_manager.group([])

    def test_group_crossing_end_boundary_raises_error(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.2, level=2
        )
        hrc4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=1
        )

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.group([hrc2, hrc4])

    def test_group_crossing_start_boundary_raises_error(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=1
        )
        hrc4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.3, level=2
        )

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.group([hrc1, hrc2])

    def test_group_overlapping_with_higher_unit_raises_error(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.2, level=2
        )

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.group([hrc1, hrc2])

    def test_group_two_units_with_parent_two_levels_higher(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.2, level=3
        )

        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc3, children=[hrc1, hrc2])
        )

        tl.component_manager.group([hrc1, hrc2])

        assert hrc1.parent == hrc2.parent
        assert not hrc1.parent == hrc3 or hrc2.parent == hrc3
        assert hrc1.parent == hrc3.children[0]

    def test_group_two_units_with_parent_that_has_parent(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.4, level=4
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.4, level=3
        )

        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )

        hrc4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )

        hrc5 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=1
        )

        hrc6 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.3, end=0.4, level=1
        )

        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc1, children=[hrc2])
        )

        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc2, children=[hrc3, hrc4, hrc5, hrc6])
        )

        tl.component_manager.group([hrc3, hrc4])

        assert hrc3.parent == hrc4.parent
        assert hrc3.parent.parent == hrc2
        assert hrc5.parent == hrc2
        assert hrc6.parent == hrc2
        assert hrc3.parent in hrc2.children
        assert hrc5 in hrc2.children
        assert hrc6 in hrc2.children

    # TEST SPLIT
    def test_get_unit_for_split_from_single_unit(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=1, level=1
        )
        unit_for_split = tl.component_manager.get_unit_to_split(0.5)

        assert unit_for_split == hrc1

    def test_get_unit_for_split_from_unit_boundary(self, tl):
        _ = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.5, level=1
        )
        _ = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.5, end=1, level=1
        )

        unit_for_split = tl.component_manager.get_unit_to_split(0.5)

        assert unit_for_split is None

    def test_get_unit_for_split_from_units_of_different_levels_spanning_time(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=1, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=1, level=2
        )
        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=1, level=3
        )

        unit_for_split = tl.component_manager.get_unit_to_split(0.5)

        assert unit_for_split is hrc1

    def test_split_unit_without_parent(self, tl_with_ui):
        hrc1 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.0, end=1, level=1
        )

        tl_with_ui.component_manager.split(hrc1, 0.5)

        assert hrc1 not in tl_with_ui.component_manager._components
        assert len(tl_with_ui.component_manager._components) == 2

    @patch(
        "tilia.timelines.hierarchy.timeline.HierarchyTimeline.update_ui_with_parent_child_relation"
    )
    def test_split_unit_with_parent(self, update_ui_parent_child_mock, tl_with_ui):
        update_ui_parent_child_mock.return_value = None

        hrc1 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.0, end=1, level=1
        )
        hrc2 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.0, end=1, level=2
        )

        tl_with_ui.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc2, children=[hrc1])
        )

        tl_with_ui.component_manager.split(hrc1, 0.5)

        assert hrc1 not in tl_with_ui.component_manager._components
        assert hrc1 not in hrc2.children
        assert len(tl_with_ui.component_manager._components) == 3
        assert len(hrc2.children) == 2

    def test_split_unit_passes_attributes(self, tl):
        """Does not test for passing of ui attributes."""
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY,
            timeline=tl,
            start=0.0,
            end=1,
            level=1,
            comments="test comment",
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY,
            timeline=tl,
            start=0.0,
            end=1,
            level=2,
        )

        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc2, children=[hrc1])
        )

        assert hrc2.children[0].comments == "test comment"

    @patch(
        "tilia.timelines.hierarchy.timeline.HierarchyTimeline.update_ui_with_parent_child_relation"
    )
    def test_split_unit_with_children(self, update_ui_parent_child_mock, tl_with_ui):
        update_ui_parent_child_mock.return_value = None

        hrc1 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.0, end=0.5, level=1
        )
        hrc2 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.5, end=1, level=1
        )
        hrc3 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0, end=1, level=2
        )

        tl_with_ui.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc3, children=[hrc1, hrc2])
        )

        tl_with_ui.component_manager.split(hrc3, 0.5)

        assert len(tl_with_ui.component_manager._components) == 4
        assert hrc1.parent
        assert hrc2.parent
        assert hrc1.parent != hrc2.parent

    # TEST MERGE
    def test_merge_two_units_without_units_between(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.5, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.5, end=1, level=1
        )

        tl.component_manager.merge([hrc1, hrc2])

        assert len(tl.component_manager._components) == 1

    def test_merge_two_units_with_units_in_between(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=1
        )
        hrc4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.3, end=0.4, level=1
        )

        tl.component_manager.merge([hrc1, hrc4])

        assert len(tl.component_manager._components) == 1

    def test_merge_three_units(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=1
        )

        tl.component_manager.merge([hrc1, hrc2, hrc3])

        assert len(tl.component_manager._components) == 1

    def test_merge_four_units(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=1
        )
        hrc4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.3, end=0.4, level=1
        )


        tl.component_manager.merge([hrc1, hrc2, hrc3, hrc4])

        assert len(tl.component_manager._components) == 1

    def test_merge_two_units_with_children(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.5, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.5, level=2
        )
        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc2, children=[hrc1])
        )
        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.5, end=1.0, level=1
        )
        hrc4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.5, end=1.0, level=2
        )
        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc4, children=[hrc3])
        )

        tl.component_manager.merge([hrc2, hrc4])

        assert hrc1.parent == hrc3.parent

    def test_merge_two_units_with_common_parent(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.5, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.5, end=1, level=1
        )
        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=2
        )

        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc3, children=[hrc1, hrc2])
        )

        tl.component_manager.merge([hrc1, hrc2])

        assert len(hrc3.children) == 1
        assert hrc1 not in hrc3.children
        assert hrc2 not in hrc3.children

    def test_merge_two_units_with_unit_with_children_in_between(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=2
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=2
        )
        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc2, children=[hrc3])
        )
        hrc4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=2
        )

        tl.component_manager.merge([hrc1, hrc4])

        assert len(tl.component_manager._components) == 2
        assert hrc3.parent.start == 0.0 and hrc3.parent.end == 0.3

    def test_merge_one_unit_raises_error(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.merge([hrc1])

    def test_merge_units_of_different_level_raises_error(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=2
        )

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.merge([hrc1, hrc2])

    def test_merge_with_unit_of_different_level_in_between_raises_error(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=2
        )
        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=1
        )

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.merge([hrc1, hrc3])

    def test_merge_with_different_parent_raises_error(self, tl):
        hrc1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        hrc2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        hrc3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=2
        )

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.merge([hrc1, hrc3])

    # TEST SERIALIZE
    # noinspection PyUnresolvedReferences
    def test_serialize_components(self, tl_with_ui):
        hrc1 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.0, end=0.1, level=1
        )
        hrc2 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.1, end=0.2, level=2
        )
        hrc3 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.2, end=0.3, level=3
        )

        serialized_components = tl_with_ui.component_manager.serialize_components()

        for unit in [hrc1, hrc2, hrc3]:
            assert serialized_components[unit.id]["start"] == unit.start
            assert serialized_components[unit.id]["end"] == unit.end
            assert serialized_components[unit.id]["level"] == unit.level

    # noinspection PyUnresolvedReferences
    def test_deserialize_components(self, tl_with_ui):
        hrc1 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.0, end=0.1, level=1
        )
        hrc2 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.1, end=0.2, level=2
        )
        hrc3 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.2, end=0.3, level=3
        )

        serialized_components = tl_with_ui.component_manager.serialize_components()

        tl_with_ui.component_manager.clear()

        tl_with_ui.component_manager.deserialize_components(serialized_components)

        assert len(tl_with_ui.component_manager._components) == 3
        assert {dsu.start for dsu in tl_with_ui.component_manager._components} == {
            u.start for u in [hrc1, hrc2, hrc3]
        }
        assert {dsu.end for dsu in tl_with_ui.component_manager._components} == {
            u.end for u in [hrc1, hrc2, hrc3]
        }
        assert {dsu.level for dsu in tl_with_ui.component_manager._components} == {
            u.level for u in [hrc1, hrc2, hrc3]
        }

    def test_deserialize_components_with_children(self, tl_with_ui):
        tl_with_ui.ui.update_parent_child_relation = lambda _: None
        tl_with_ui.ui.rearrange_canvas_drawings = lambda: None

        hrc1 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.0, end=0.3, level=1
        )
        hrc2 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.1, end=0.2, level=2
        )
        hrc3 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.2, end=0.3, level=3
        )

        tl_with_ui.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=hrc1, children=[hrc2, hrc3])
        )

        serialized_components = tl_with_ui.component_manager.serialize_components()

        tl_with_ui.component_manager.clear()

        tl_with_ui.component_manager.deserialize_components(serialized_components)

        dsrl_hrc1, dsrl_hrc2, dsrl_hrc3 = sorted(
            list(tl_with_ui.component_manager._components), key=lambda x: x.start
        )

        assert dsrl_hrc2 in dsrl_hrc1.children
        assert dsrl_hrc3 in dsrl_hrc1.children
        assert dsrl_hrc2.parent == dsrl_hrc1
        assert dsrl_hrc3.parent == dsrl_hrc1

    # TEST CROP
    def test_crop(self, tl_with_ui):

        hrc1 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.0, end=0.3, level=1
        )

        hrc2 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.1, end=0.2, level=2
        )

        hrc3 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.2, end=0.3, level=3
        )

        hrc4 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.0, end=0.1, level=1
        )

        tl_with_ui.component_manager.crop(0.15)

        assert len(tl_with_ui.component_manager._components) == 3
        assert hrc1.start == 0.0
        assert hrc1.end == 0.15
        assert hrc2.start == 0.1
        assert hrc2.end == 0.15
        assert hrc4.start == 0.0
        assert hrc4.end == 0.1

    def test_scale(self, tl_with_ui):

        hrc1 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0, end=1, level=1
        )

        hrc2 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=1, end=3, level=2
        )

        hrc3 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=3, end=6, level=3
        )

        tl_with_ui.component_manager.scale(0.5)

        assert len(tl_with_ui.component_manager._components) == 3
        assert hrc1.start == 0
        assert hrc1.end == 0.5
        assert hrc2.start == 0.5
        assert hrc2.end == 1.5
        assert hrc3.start == 1.5
        assert hrc3.end == 3
