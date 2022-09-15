import pytest

from unittest.mock import MagicMock, ANY, patch
import itertools
import logging

from tilia.timelines.collection import TimelineCollection
from tilia.timelines.common import InvalidComponentKindError
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.hierarchy.components import HierarchyOperationError, Hierarchy
from tilia.timelines.hierarchy.timeline import (
    HierarchyTLComponentManager,
    HierarchyTimeline,
)
from tilia.timelines.hierarchy.common import ParentChildRelation

# noinspection PyProtectedMember
from tilia.timelines.serialize import serialize_component, _deserialize_component
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.element_kinds import UIElementKind
from tilia.ui.tkinter.timelines.common import (
    TimelineUIElementManager,
    TkTimelineUICollection,
)
from tilia.ui.tkinter.timelines.hierarchy import HierarchyTimelineTkUI, HierarchyTkUI
from tilia.ui.tkinter.timelines.hierarchy.copy_paste_manager import HierarchyTimelineCopyPasteManager

logger = logging.getLogger(__name__)


@pytest.fixture
def tl_with_ui() -> HierarchyTimeline:

    id_counter = itertools.count()

    tl_coll_mock = MagicMock()
    tl_coll_mock.get_id = lambda: next(id_counter)

    tlui_coll_mock = MagicMock()
    tlui_coll_mock.get_id = lambda: next(id_counter)

    component_manager = HierarchyTLComponentManager()
    copy_paste_manager = HierarchyTimelineCopyPasteManager()
    timeline = HierarchyTimeline(tl_coll_mock, component_manager)

    timeline.ui = HierarchyTimelineTkUI(
        timeline_ui_collection=tlui_coll_mock,
        element_manager=TimelineUIElementManager(
            HierarchyTimelineTkUI.ELEMENT_KINDS_TO_ELEMENT_CLASSES
        ),
        copy_paste_manager=copy_paste_manager,
        canvas=MagicMock(),
        toolbar=MagicMock(),
        name="",
    )
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

    # TEST CREATE
    def test_delete_hierarchy(self, tl):
        unit1 = tl.create_timeline_component(
            ComponentKind.HIERARCHY, 0, 1, 1
        )

        tl.on_request_to_delete_component(unit1)

        assert not tl.component_manager._components

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

        unit1 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, **unit_kwargs
        )

        # noinspection PyTypeChecker
        srlz_unit1 = serialize_component(unit1)

        for key, value in unit_kwargs.items():
            assert srlz_unit1[key] == value

        assert srlz_unit1["parent"] is None
        assert srlz_unit1["children"] == []

    def test_serialize_unit_with_parent(self, tl):

        unit1 = tl.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 1)

        unit2 = tl.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 2)

        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=unit2, children=[unit1])
        )
        # noinspection PyTypeChecker
        srlz_unit1 = serialize_component(unit1)

        assert srlz_unit1["parent"] == unit2.id

    def test_serialize_unit_with_children(self, tl):

        unit1 = tl.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 1)

        unit2 = tl.create_timeline_component(ComponentKind.HIERARCHY, 0.5, 1, 1)

        unit3 = tl.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 2)

        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=unit3, children=[unit1, unit2])
        )
        # noinspection PyTypeChecker
        srlz_unit3 = serialize_component(unit3)

        assert set(srlz_unit3["children"]) == {unit1.id, unit2.id}

    def test_deserialize_unit(self, tl_with_ui):
        unit_kwargs = {
            "start": 0,
            "end": 1,
            "level": 1,
            "comments": "my comments",
            "formal_type": "my formal type",
            "formal_function": "my formal function",
        }

        unit1 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, **unit_kwargs
        )

        # noinspection PyTypeChecker
        serialized_unit1 = serialize_component(unit1)

        deserialized_unit1 = _deserialize_component(tl_with_ui, serialized_unit1)

        for attr in unit_kwargs:
            assert getattr(unit1, attr) == getattr(deserialized_unit1, attr)

    def test_deserialize_unit_with_serializable_by_ui_attributes(self, tl_with_ui):
        serializable_by_ui_attrs = {"color": "#000000", "label": "my label"}

        unit1 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, 0, 1, 1, **serializable_by_ui_attrs
        )

        # noinspection PyTypeChecker
        serialized_unit1 = serialize_component(unit1)

        deserialized_unit1 = _deserialize_component(tl_with_ui, serialized_unit1)

        for attr in serializable_by_ui_attrs:
            assert getattr(unit1.ui, attr) == getattr(deserialized_unit1.ui, attr)

    # noinspection PyTypeChecker, PyUnresolvedReferences
    @patch(
        "tilia.timelines.hierarchy.timeline.HierarchyTimeline.update_ui_with_parent_child_relation"
    )
    def test_deserialize_unit_with_parent(
        self, update_ui_parent_child_mock, tl_with_ui
    ):

        unit1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 1)

        unit2 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 2)

        tl_with_ui.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=unit2, children=[unit1])
        )

        serialized_unit1 = serialize_component(unit1)

        update_ui_parent_child_mock.return_value = None

        deserialized_unit1 = _deserialize_component(tl_with_ui, serialized_unit1)

        assert deserialized_unit1.parent == unit2.id

    # noinspection PyTypeChecker, PyUnresolvedReferences
    @patch(
        "tilia.timelines.hierarchy.timeline.HierarchyTimeline.update_ui_with_parent_child_relation"
    )
    def test_deserialize_unit_with_children(
        self, update_ui_parent_child_mock, tl_with_ui
    ):

        unit1 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 1)

        unit2 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0.5, 1, 1)

        unit3 = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 1, 2)

        tl_with_ui.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=unit3, children=[unit1, unit2])
        )

        serialized_unit3 = serialize_component(unit3)

        update_ui_parent_child_mock.return_value = None

        deserialized_unit3 = _deserialize_component(tl_with_ui, serialized_unit3)

        assert deserialized_unit3.children == [unit1.id, unit2.id]

    def test_serialize_timeline(self, tl_with_ui):
        _ = tl_with_ui.create_timeline_component(ComponentKind.HIERARCHY, 0, 0.5, 1)

        serialized_timeline = tl_with_ui.to_dict()

        assert serialized_timeline["height"] == HierarchyTimelineTkUI.DEFAULT_HEIGHT
        assert serialized_timeline["is_visible"] is True
        assert serialized_timeline["kind"] == TimelineKind.HIERARCHY_TIMELINE.name
        assert len(serialized_timeline["components"])


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

        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0, end=0.1, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )

        tl.component_manager.group([unit1, unit2])

        assert unit1.parent == unit2.parent
        assert unit1.parent.level == 2

    def test_group_two_units_out_of_order(self, tl):

        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0, end=0.1, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )

        tl.component_manager.group([unit2, unit1])

        assert unit1.parent == unit2.parent

    def test_group_two_units_with_units_of_same_level_in_between(self, tl):

        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0, end=0.1, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        unit3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=1
        )
        unit4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.3, end=0.4, level=1
        )

        tl.component_manager.group([unit1, unit4])

        assert unit1.parent == unit2.parent == unit3.parent == unit4.parent

    def test_group_two_units_with_units_of_different_level_in_between(self, tl):

        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0, end=0.1, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=2
        )
        unit3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=3
        )
        unit4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.3, end=0.4, level=1
        )

        tl.component_manager.group([unit1, unit4])

        assert unit1.parent == unit2.parent == unit3.parent == unit4.parent
        assert unit1.parent.level == 4

    def test_group_two_units_with_unit_with_children_in_between(self, tl):

        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0, end=0.1, level=2
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        unit3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=1
        )
        unit4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.3, level=2
        )
        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=unit4, children=[unit2, unit3])
        )
        unit5 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.3, end=0.4, level=2
        )

        tl.component_manager.group([unit1, unit5])

        assert unit1.parent == unit4.parent == unit5.parent

    def test_group_three_units_with_units_between_grouped_units(self, tl):

        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0, end=0.1, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        unit3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=1
        )
        unit4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.3, end=0.4, level=1
        )
        unit5 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.4, end=0.5, level=1
        )

        tl.component_manager.group([unit1, unit3, unit5])

        assert unit1.parent == unit2.parent == unit3.parent == unit4.parent

    def test_group_one_unit_raises_error(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0, end=0.1, level=1
        )
        with pytest.raises(HierarchyOperationError):
            tl.component_manager.group([unit1])

    def test_group_empty_list_raises_error(self, tl):
        with pytest.raises(HierarchyOperationError):
            tl.component_manager.group([])

    def test_group_crossing_end_boundary_raises_error(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        unit3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.2, level=2
        )
        unit4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=1
        )

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.group([unit2, unit4])

    def test_group_crossing_start_boundary_raises_error(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        unit3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=1
        )
        unit4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.3, level=2
        )

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.group([unit1, unit2])

    def test_group_overlapping_with_higher_unit_raises_error(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        unit3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.2, level=2
        )

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.group([unit1, unit2])

    def test_group_two_units_with_parent_two_levels_higher(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        unit3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.2, level=3
        )

        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=unit3, children=[unit1, unit2])
        )

        tl.component_manager.group([unit1, unit2])

        assert unit1.parent == unit2.parent
        assert not unit1.parent == unit3 or unit2.parent == unit3
        assert unit1.parent == unit3.children[0]

    # TEST SPLIT
    def test_get_unit_for_split_from_single_unit(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=1, level=1
        )
        unit_for_split = tl.component_manager.get_unit_to_split(0.5)

        assert unit_for_split == unit1

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
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=1, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=1, level=2
        )
        unit3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=1, level=3
        )

        unit_for_split = tl.component_manager.get_unit_to_split(0.5)

        assert unit_for_split is unit1

    def test_split_unit_without_parent(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=1, level=1
        )

        tl.component_manager.split(unit1, 0.5)

        assert unit1 not in tl.component_manager._components
        assert len(tl.component_manager._components) == 2

    def test_split_unit_with_parent(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=1, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=1, level=2
        )

        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=unit2, children=[unit1])
        )

        tl.component_manager.split(unit1, 0.5)

        assert unit1 not in tl.component_manager._components
        assert unit1 not in unit2.children
        assert len(tl.component_manager._components) == 3
        assert len(unit2.children) == 2

    def test_split_unit_with_children(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.5, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.5, end=1, level=1
        )
        unit3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0, end=1, level=2
        )

        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=unit3, children=[unit1, unit2])
        )

        tl.component_manager.split(unit3, 0.5)

        assert len(tl.component_manager._components) == 4
        assert unit1.parent
        assert unit2.parent
        assert unit1.parent != unit2.parent

    # TEST MERGE
    def test_merge_two_units_without_units_between(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.5, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.5, end=1, level=1
        )

        tl.component_manager.merge([unit1, unit2])

        assert len(tl.component_manager._components) == 1

    def test_merge_two_units_with_units_in_between(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        unit3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=1
        )
        unit4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.3, end=0.4, level=1
        )

        tl.component_manager.merge([unit1, unit4])

        assert len(tl.component_manager._components) == 1

    def test_merge_two_units_with_children(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.5, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.5, level=2
        )
        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=unit2, children=[unit1])
        )
        unit3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.5, end=1.0, level=1
        )
        unit4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.5, end=1.0, level=2
        )
        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=unit4, children=[unit3])
        )

        tl.component_manager.merge([unit2, unit4])

        assert unit1.parent == unit3.parent

    def test_merge_two_units_with_common_parent(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.5, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.5, end=1, level=1
        )
        unit3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=2
        )

        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=unit3, children=[unit1, unit2])
        )

        tl.component_manager.merge([unit1, unit2])

        assert len(unit3.children) == 1
        assert unit1 not in unit3.children
        assert unit2 not in unit3.children

    def test_merge_two_units_with_unit_with_children_in_between(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=2
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=2
        )
        unit3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        tl.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=unit2, children=[unit3])
        )
        unit4 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=2
        )

        tl.component_manager.merge([unit1, unit4])

        assert len(tl.component_manager._components) == 2
        assert unit3.parent.start == 0.0 and unit3.parent.end == 0.3

    def test_merge_one_unit_raises_error(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.merge([unit1])

    def test_merge_units_of_different_level_raises_error(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=2
        )

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.merge([unit1, unit2])

    def test_merge_with_unit_of_different_level_in_between_raises_error(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=2
        )
        unit3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.2, end=0.3, level=1
        )

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.merge([unit1, unit3])

    def test_merge_with_different_parent_raises_error(self, tl):
        unit1 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.0, end=0.1, level=1
        )
        unit2 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=1
        )
        unit3 = tl.component_manager.create_component(
            ComponentKind.HIERARCHY, timeline=tl, start=0.1, end=0.2, level=2
        )

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.merge([unit1, unit3])

    # TEST SERIALIZE
    # noinspection PyUnresolvedReferences
    def test_serialize_components(self, tl_with_ui):
        unit1 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.0, end=0.1, level=1
        )
        unit2 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.1, end=0.2, level=2
        )
        unit3 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.2, end=0.3, level=3
        )

        serialized_components = tl_with_ui.component_manager.serialize_components()

        for unit in [unit1, unit2, unit3]:
            assert serialized_components[unit.id]["start"] == unit.start
            assert serialized_components[unit.id]["end"] == unit.end
            assert serialized_components[unit.id]["level"] == unit.level

    # noinspection PyUnresolvedReferences
    def test_deserialize_components(self, tl_with_ui):
        unit1 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.0, end=0.1, level=1
        )
        unit2 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.1, end=0.2, level=2
        )
        unit3 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.2, end=0.3, level=3
        )

        serialized_components = tl_with_ui.component_manager.serialize_components()

        tl_with_ui.component_manager.clear()

        tl_with_ui.component_manager.deserialize_components(serialized_components)

        assert len(tl_with_ui.component_manager._components) == 3
        assert {dsu.start for dsu in tl_with_ui.component_manager._components} == {
            u.start for u in [unit1, unit2, unit3]
        }
        assert {dsu.end for dsu in tl_with_ui.component_manager._components} == {
            u.end for u in [unit1, unit2, unit3]
        }
        assert {dsu.level for dsu in tl_with_ui.component_manager._components} == {
            u.level for u in [unit1, unit2, unit3]
        }

    def test_deserialize_components_with_children(self, tl_with_ui):
        tl_with_ui.ui.update_parent_child_relation = lambda _: None
        tl_with_ui.ui.rearrange_canvas_drawings = lambda: None

        unit1 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.0, end=0.3, level=1
        )
        unit2 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.1, end=0.2, level=2
        )
        unit3 = tl_with_ui.create_timeline_component(
            ComponentKind.HIERARCHY, start=0.2, end=0.3, level=3
        )

        tl_with_ui.component_manager._make_parent_child_relation(
            ParentChildRelation(parent=unit1, children=[unit2, unit3])
        )


        serialized_components = tl_with_ui.component_manager.serialize_components()

        tl_with_ui.component_manager.clear()

        tl_with_ui.component_manager.deserialize_components(serialized_components)

        dsrl_unit1, dsrl_unit2, dsrl_unit3 = sorted(list(tl_with_ui.component_manager._components), key=lambda x: x.start)

        assert dsrl_unit2 in dsrl_unit1.children
        assert dsrl_unit3 in dsrl_unit1.children
        assert dsrl_unit2.parent == dsrl_unit1
        assert dsrl_unit3.parent == dsrl_unit1
