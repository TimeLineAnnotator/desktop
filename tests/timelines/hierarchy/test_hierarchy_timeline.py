import pytest
import itertools
import logging

from tilia.exceptions import InvalidComponentKindError
from tilia.timelines.hierarchy.components import HierarchyOperationError
from tilia.timelines.hierarchy.timeline import (
    HierarchyTLComponentManager,
    HierarchyTimeline,
)

# noinspection PyProtectedMember
from tilia.timelines.serialize import serialize_component, _deserialize_component
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.hierarchy import HierarchyTimelineUI

logger = logging.getLogger(__name__)


class HierarchyUIDummy:
    def __init__(self, component, **kwargs):
        self.tl_component = component
        for attr, value in kwargs.items():
            setattr(self, attr, value)

    def update_position(self):
        return

    def process_color_before_level_change(self, *args, **kwargs):
        return


class DummyTimelines:
    ID_ITER = itertools.count()

    def get_id(self):
        return next(self.ID_ITER)

    def get_media_length(self):
        return 100


@pytest.fixture
def tl(hierarchy_tl) -> HierarchyTimeline:
    return hierarchy_tl


@pytest.fixture
def cm(tl) -> HierarchyTLComponentManager:
    return tl.component_manager


class TkFontDummy:
    def measure(self, _):
        return 0


class TestHierarchyTimeline:
    # TEST CREATE
    def test_create_hierarchy(self, tl):
        tl.create_hierarchy(start=0, end=1, level=1)

        assert len(tl.component_manager._components) == 1

    # TEST DELETE
    def test_delete_hierarchy(self, tl):
        hrc1 = tl.create_hierarchy(0, 1, 1)

        tl.on_request_to_delete_components([hrc1])

        assert not tl.component_manager._components

    # TEST SERIALIZE
    def test_serialize_unit(self, tl):
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

        hrc1 = tl.create_hierarchy(**unit_kwargs)

        # noinspection PyTypeChecker
        srlz_hrc1 = serialize_component(hrc1)

        for key, value in unit_kwargs.items():
            assert srlz_hrc1[key] == value

        assert srlz_hrc1["parent"] is None
        assert srlz_hrc1["children"] == []

    def test_serialize_unit_with_parent(self, tl):
        hrc1 = tl.create_hierarchy(0, 1, 1)

        hrc2 = tl.create_hierarchy(0, 1, 2)

        tl.component_manager._update_genealogy(hrc2, [hrc1])
        # noinspection PyTypeChecker
        srlz_hrc1 = serialize_component(hrc1)

        assert srlz_hrc1["parent"] == hrc2.id

    def test_serialize_unit_with_children(self, tl):
        hrc1 = tl.create_hierarchy(0, 0.5, 1)

        hrc2 = tl.create_hierarchy(0.5, 1, 1)

        hrc3 = tl.create_hierarchy(0, 1, 2)

        tl.component_manager._update_genealogy(hrc3, [hrc1, hrc2])
        # noinspection PyTypeChecker
        srlz_hrc3 = serialize_component(hrc3)

        assert set(srlz_hrc3["children"]) == {hrc1.id, hrc2.id}

    def test_deserialize_unit(self, tl):
        unit_kwargs = {
            "start": 0,
            "end": 1,
            "level": 1,
            "label": "my label",
            "comments": "my comments",
            "formal_type": "my formal type",
            "formal_function": "my formal function",
            "color": "#000000",
        }

        hrc1 = tl.create_hierarchy(**unit_kwargs)

        # noinspection PyTypeChecker
        serialized_hrc1 = serialize_component(hrc1)

        deserialized_hrc1 = _deserialize_component(tl, serialized_hrc1)

        for attr in unit_kwargs:
            assert getattr(hrc1, attr) == getattr(deserialized_hrc1, attr)

    # noinspection PyTypeChecker, PyUnresolvedReferences

    def test_deserialize_unit_with_parent(self, tl):
        hrc1 = tl.create_hierarchy(0, 1, 1)

        hrc2 = tl.create_hierarchy(0, 1, 2)

        tl.component_manager._update_genealogy(hrc2, [hrc1])

        serialized_hrc1 = serialize_component(hrc1)

        deserialized_hrc1 = _deserialize_component(tl, serialized_hrc1)

        assert deserialized_hrc1.parent == hrc2.id

        # teardown can't happen if these properties are strings
        deserialized_hrc1.parent = None
        deserialized_hrc1.children = []

    # noinspection PyTypeChecker, PyUnresolvedReferences
    def test_deserialize_unit_with_children(self, tl):
        hrc1 = tl.create_hierarchy(0, 0.5, 1)
        hrc2 = tl.create_hierarchy(0.5, 1, 1)
        hrc3 = tl.create_hierarchy(0, 1, 2)

        tl.component_manager._update_genealogy(hrc3, [hrc1, hrc2])

        serialized_hrc3 = serialize_component(hrc3)

        deserialized_hrc3 = _deserialize_component(tl, serialized_hrc3)

        assert deserialized_hrc3.children == [hrc1.id, hrc2.id]

        # teardown can't happen if these properties are strings
        deserialized_hrc3.parent = None
        deserialized_hrc3.children = []

    def test_serialize_timeline(self, tl):
        tl.create_hierarchy(0, 0.5, 1)

        serialized_timeline = tl.get_state()

        assert serialized_timeline["height"] == HierarchyTimelineUI.DEFAULT_HEIGHT
        assert serialized_timeline["is_visible"] is True
        assert serialized_timeline["kind"] == TimelineKind.HIERARCHY_TIMELINE.name
        assert len(serialized_timeline["components"])

    # TEST UNDO
    def test_restore_state(self, tl):
        hrc1 = tl.create_hierarchy(0, 1, 1)
        hrc2 = tl.create_hierarchy(1, 2, 1)

        state = tl.get_state()

        tl.on_request_to_delete_components([hrc1, hrc2])

        assert len(tl.component_manager._components) == 0

        tl.restore_state(state)

        assert len(tl.component_manager._components) == 2


class TestHierarchyTimelineComponentManager:
    def test_create_invalid_component_kind_raises_error(self, tl):
        with pytest.raises(InvalidComponentKindError):
            # noinspection PyTypeChecker
            tl.component_manager.create_component(
                "INVALID KIND", start=0, end=1, level=1
            )

    def test_create_unit_below(self, tl):
        parent = tl.create_hierarchy(start=0, end=1, level=3)
        child = tl.create_hierarchy(start=0, end=1, level=1)

        tl.component_manager._update_genealogy(parent, [child])

        tl.component_manager.create_unit_below(parent)

        assert child.parent in parent.children

    # TEST CLEAR
    def test_clear(self, tl):
        tl.create_hierarchy(start=0.0, end=0.1, level=1)
        tl.create_hierarchy(start=0.1, end=0.2, level=2)
        tl.create_hierarchy(start=0.2, end=0.3, level=3)

        tl.component_manager.clear()

        assert not tl.component_manager._components

    # TEST GROUP
    def test_group_two_units(self, tl):
        hrc1 = tl.create_hierarchy(start=0, end=0.1, level=1)
        hrc2 = tl.create_hierarchy(start=0.1, end=0.2, level=1)

        tl.component_manager.group([hrc1, hrc2])

        assert hrc1.parent == hrc2.parent
        assert hrc1.parent.level == 2

    def test_group_two_units_out_of_order(self, tl):
        hrc1 = tl.create_hierarchy(start=0, end=0.1, level=1)
        hrc2 = tl.create_hierarchy(start=0.1, end=0.2, level=1)

        tl.component_manager.group([hrc2, hrc1])

        assert hrc1.parent == hrc2.parent

    def test_group_two_units_with_units_of_same_level_in_between(self, tl):
        hrc1 = tl.create_hierarchy(start=0, end=0.1, level=1)
        hrc2 = tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hrc3 = tl.create_hierarchy(start=0.2, end=0.3, level=1)
        hrc4 = tl.create_hierarchy(start=0.3, end=0.4, level=1)

        tl.component_manager.group([hrc1, hrc4])

        assert hrc1.parent == hrc2.parent == hrc3.parent == hrc4.parent

    def test_group_two_units_with_units_of_different_level_in_between(self, tl):
        hrc1 = tl.create_hierarchy(start=0, end=0.1, level=1)
        hrc2 = tl.create_hierarchy(start=0.1, end=0.2, level=2)
        hrc3 = tl.create_hierarchy(start=0.2, end=0.3, level=3)
        hrc4 = tl.create_hierarchy(start=0.3, end=0.4, level=1)

        tl.component_manager.group([hrc1, hrc4])

        assert hrc1.parent == hrc2.parent == hrc3.parent == hrc4.parent
        assert hrc1.parent.level == 4

    def test_group_two_units_with_unit_with_children_in_between(self, tl):
        hrc1 = tl.create_hierarchy(start=0, end=0.1, level=2)
        hrc2 = tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hrc3 = tl.create_hierarchy(start=0.2, end=0.3, level=1)
        hrc4 = tl.create_hierarchy(start=0.1, end=0.3, level=2)
        tl.component_manager._update_genealogy(hrc4, [hrc2, hrc3])
        hrc5 = tl.create_hierarchy(start=0.3, end=0.4, level=2)

        tl.component_manager.group([hrc1, hrc5])

        assert hrc1.parent == hrc4.parent == hrc5.parent

    def test_group_three_units_with_units_between_grouped_units(self, tl):
        hrc1 = tl.create_hierarchy(start=0, end=0.1, level=1)
        hrc2 = tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hrc3 = tl.create_hierarchy(start=0.2, end=0.3, level=1)
        hrc4 = tl.create_hierarchy(start=0.3, end=0.4, level=1)
        hrc5 = tl.create_hierarchy(start=0.4, end=0.5, level=1)

        tl.component_manager.group([hrc1, hrc3, hrc5])

        assert hrc1.parent == hrc2.parent == hrc3.parent == hrc4.parent

    def test_group_one_unit_raises_error(self, tl):
        hrc1 = tl.create_hierarchy(start=0, end=0.1, level=1)
        with pytest.raises(HierarchyOperationError):
            tl.component_manager.group([hrc1])

    def test_group_empty_list_raises_error(self, tl):
        with pytest.raises(HierarchyOperationError):
            tl.component_manager.group([])

    def test_group_crossing_end_boundary_raises_error(self, tl):
        tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2 = tl.create_hierarchy(start=0.1, end=0.2, level=1)
        tl.create_hierarchy(start=0.0, end=0.2, level=2)
        hrc4 = tl.create_hierarchy(start=0.2, end=0.3, level=1)

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.group([hrc2, hrc4])

    def test_group_crossing_start_boundary_raises_error(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2 = tl.create_hierarchy(start=0.1, end=0.2, level=1)
        tl.create_hierarchy(start=0.2, end=0.3, level=1)
        tl.create_hierarchy(start=0.1, end=0.3, level=2)

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.group([hrc1, hrc2])

    def test_group_overlapping_with_higher_unit_raises_error(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2 = tl.create_hierarchy(start=0.1, end=0.2, level=1)
        tl.create_hierarchy(start=0.0, end=0.2, level=2)

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.group([hrc1, hrc2])

    def test_group_two_units_with_parent_two_levels_higher(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2 = tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hrc3 = tl.create_hierarchy(start=0.0, end=0.2, level=3)

        tl.component_manager._update_genealogy(hrc3, [hrc1, hrc2])

        tl.component_manager.group([hrc1, hrc2])

        assert hrc1.parent == hrc2.parent
        assert not hrc1.parent == hrc3 or hrc2.parent == hrc3
        assert hrc1.parent in hrc3.children

    def test_group_two_units_with_parent_that_has_parent(self, hierarchy_tl):
        tl = hierarchy_tl
        hrc1 = tl.create_hierarchy(start=0.0, end=0.4, level=4)
        hrc2 = tl.create_hierarchy(start=0.0, end=0.4, level=3)
        hrc3 = tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc4 = tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hrc5 = tl.create_hierarchy(start=0.2, end=0.3, level=1)
        hrc6 = tl.create_hierarchy(start=0.3, end=0.4, level=1)

        tl.component_manager._update_genealogy(hrc1, [hrc2])

        tl.component_manager._update_genealogy(hrc2, [hrc3, hrc4, hrc5, hrc6])

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
        hrc1 = tl.create_hierarchy(start=0.0, end=1, level=1)
        unit_for_split = tl.component_manager.get_unit_to_split(0.5)

        assert unit_for_split == hrc1

    def test_get_unit_for_split_from_unit_boundary(self, tl):
        tl.create_hierarchy(start=0.0, end=0.5, level=1)
        tl.create_hierarchy(start=0.5, end=1, level=1)

        unit_for_split = tl.component_manager.get_unit_to_split(0.5)

        assert unit_for_split is None

    def test_get_unit_for_split_from_units_of_different_levels_spanning_time(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=1, level=1)
        tl.create_hierarchy(start=0.0, end=1, level=2)
        tl.create_hierarchy(start=0.0, end=1, level=3)

        unit_for_split = tl.component_manager.get_unit_to_split(0.5)

        assert unit_for_split is hrc1

    def test_split_unit_without_parent(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=1, level=1)

        tl.component_manager.split(hrc1, 0.5)

        assert hrc1 not in tl.component_manager._components
        assert len(tl.component_manager._components) == 2

    def test_split_unit_with_parent(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=1, level=1)
        hrc2 = tl.create_hierarchy(start=0.0, end=1, level=2)

        tl.component_manager._update_genealogy(hrc2, [hrc1])

        tl.component_manager.split(hrc1, 0.5)

        assert hrc1 not in tl.component_manager._components
        assert hrc1 not in hrc2.children
        assert len(tl.component_manager._components) == 3
        assert len(hrc2.children) == 2

    def test_split_unit_passes_attributes(self, tl):
        """Does not test for passing of ui attributes."""
        hrc1 = tl.create_hierarchy(
            start=0.0,
            end=1,
            level=1,
            comments="test comment",
        )
        hrc2 = tl.create_hierarchy(
            start=0.0,
            end=1,
            level=2,
        )

        tl.component_manager._update_genealogy(hrc2, [hrc1])

        assert hrc2.children[0].comments == "test comment"

    def test_split_unit_with_children(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.5, level=1)
        hrc2 = tl.create_hierarchy(start=0.5, end=1, level=1)
        hrc3 = tl.create_hierarchy(start=0, end=1, level=2)

        tl.component_manager._update_genealogy(hrc3, [hrc1, hrc2])

        tl.component_manager.split(hrc3, 0.5)

        assert len(tl.component_manager._components) == 4
        assert hrc1.parent
        assert hrc2.parent
        assert hrc1.parent != hrc2.parent

    # TEST MERGE
    def test_merge_two_units_without_units_between(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.5, level=1)
        hrc2 = tl.create_hierarchy(start=0.5, end=1, level=1)

        tl.component_manager.merge([hrc1, hrc2])

        assert len(tl.component_manager._components) == 1

    def test_merge_two_units_with_units_in_between(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.1, level=1)
        tl.create_hierarchy(start=0.1, end=0.2, level=1)
        tl.create_hierarchy(start=0.2, end=0.3, level=1)
        hrc4 = tl.create_hierarchy(start=0.3, end=0.4, level=1)

        tl.component_manager.merge([hrc1, hrc4])

        assert len(tl.component_manager._components) == 1

    def test_merge_three_units(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2 = tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hrc3 = tl.create_hierarchy(start=0.2, end=0.3, level=1)

        tl.component_manager.merge([hrc1, hrc2, hrc3])

        assert len(tl.component_manager._components) == 1

    def test_merge_four_units(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2 = tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hrc3 = tl.create_hierarchy(start=0.2, end=0.3, level=1)
        hrc4 = tl.create_hierarchy(start=0.3, end=0.4, level=1)

        tl.component_manager.merge([hrc1, hrc2, hrc3, hrc4])

        assert len(tl.component_manager._components) == 1

    def test_merge_two_units_with_children(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.5, level=1)
        hrc2 = tl.create_hierarchy(start=0.0, end=0.5, level=2)
        tl.component_manager._update_genealogy(hrc2, [hrc1])
        hrc3 = tl.create_hierarchy(start=0.5, end=1.0, level=1)
        hrc4 = tl.create_hierarchy(start=0.5, end=1.0, level=2)
        tl.component_manager._update_genealogy(hrc4, [hrc3])

        tl.component_manager.merge([hrc2, hrc4])

        assert hrc1.parent == hrc3.parent

    def test_merge_two_units_with_common_parent(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.5, level=1)
        hrc2 = tl.create_hierarchy(start=0.5, end=1, level=1)
        hrc3 = tl.create_hierarchy(start=0.0, end=1, level=2)

        tl.component_manager._update_genealogy(hrc3, [hrc1, hrc2])

        tl.component_manager.merge([hrc1, hrc2])

        assert len(hrc3.children) == 1
        assert hrc1 not in hrc3.children
        assert hrc2 not in hrc3.children

    def test_merge_two_units_with_unit_with_children_in_between(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.1, level=2)
        hrc2 = tl.create_hierarchy(start=0.1, end=0.2, level=2)
        hrc3 = tl.create_hierarchy(start=0.1, end=0.2, level=1)
        tl.component_manager._update_genealogy(hrc2, [hrc3])
        hrc4 = tl.create_hierarchy(start=0.2, end=0.3, level=2)

        tl.component_manager.merge([hrc1, hrc4])

        assert len(tl.component_manager._components) == 2
        assert hrc3.parent.start == 0.0 and hrc3.parent.end == 0.3

    def test_merge_one_unit_raises_error(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.1, level=1)

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.merge([hrc1])

    def test_merge_units_of_different_level_raises_error(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2 = tl.create_hierarchy(start=0.1, end=0.2, level=2)

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.merge([hrc1, hrc2])

    def test_merge_with_unit_of_different_level_in_between_raises_error(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.1, level=1)
        tl.create_hierarchy(start=0.1, end=0.2, level=2)
        hrc3 = tl.create_hierarchy(start=0.2, end=0.3, level=1)

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.merge([hrc1, hrc3])

    def test_merge_with_different_parent_raises_error(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.1, level=1)
        tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hrc3 = tl.create_hierarchy(start=0.1, end=0.2, level=2)

        with pytest.raises(HierarchyOperationError):
            tl.component_manager.merge([hrc1, hrc3])

    # TEST SERIALIZE
    # noinspection PyUnresolvedReferences
    def test_serialize_components(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2 = tl.create_hierarchy(start=0.1, end=0.2, level=2)
        hrc3 = tl.create_hierarchy(start=0.2, end=0.3, level=3)

        serialized_components = tl.component_manager.serialize_components()

        for unit in [hrc1, hrc2, hrc3]:
            assert serialized_components[unit.id]["start"] == unit.start
            assert serialized_components[unit.id]["end"] == unit.end
            assert serialized_components[unit.id]["level"] == unit.level

    # noinspection PyUnresolvedReferences
    def test_deserialize_components(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2 = tl.create_hierarchy(start=0.1, end=0.2, level=2)
        hrc3 = tl.create_hierarchy(start=0.2, end=0.3, level=3)

        serialized_components = tl.component_manager.serialize_components()

        tl.component_manager.clear()

        tl.component_manager.deserialize_components(serialized_components)

        assert len(tl.component_manager._components) == 3
        assert {dsu.start for dsu in tl.component_manager._components} == {
            u.start for u in [hrc1, hrc2, hrc3]
        }
        assert {dsu.end for dsu in tl.component_manager._components} == {
            u.end for u in [hrc1, hrc2, hrc3]
        }
        assert {dsu.level for dsu in tl.component_manager._components} == {
            u.level for u in [hrc1, hrc2, hrc3]
        }

    def test_deserialize_components_with_children(self, tl):
        hrc1 = tl.create_hierarchy(start=0, end=1, level=1)
        hrc2 = tl.create_hierarchy(start=1, end=2, level=2)
        hrc3 = tl.create_hierarchy(start=0, end=2, level=3)

        tl.component_manager._update_genealogy(hrc3, [hrc1, hrc2])

        serialized_components = tl.component_manager.serialize_components()

        tl.clear()

        tl.component_manager.deserialize_components(serialized_components)

        dsrl_hrc1, dsrl_hrc2, dsrl_hrc3 = sorted(
            list(tl.component_manager._components), key=lambda x: x.level
        )

        assert dsrl_hrc1 in dsrl_hrc3.children
        assert dsrl_hrc2 in dsrl_hrc3.children
        assert dsrl_hrc1.parent == dsrl_hrc3
        assert dsrl_hrc2.parent == dsrl_hrc3

        tl.clear()

    # TEST CROP
    def test_crop(self, tl):
        hrc1 = tl.create_hierarchy(start=0.0, end=0.3, level=1)

        hrc2 = tl.create_hierarchy(start=0.1, end=0.2, level=2)

        tl.create_hierarchy(start=0.2, end=0.3, level=3)

        hrc4 = tl.create_hierarchy(start=0.0, end=0.1, level=1)

        tl.component_manager.crop(0.15)

        assert len(tl.component_manager._components) == 3
        assert hrc1.start == 0.0
        assert hrc1.end == 0.15
        assert hrc2.start == 0.1
        assert hrc2.end == 0.15
        assert hrc4.start == 0.0
        assert hrc4.end == 0.1

    def test_scale(self, tl):
        hrc1 = tl.create_hierarchy(start=0, end=1, level=1)
        hrc2 = tl.create_hierarchy(start=1, end=3, level=2)
        hrc3 = tl.create_hierarchy(start=3, end=6, level=3)

        tl.component_manager.scale(0.5)

        assert len(tl.component_manager._components) == 3
        assert hrc1.start == 0
        assert hrc1.end == 0.5
        assert hrc2.start == 0.5
        assert hrc2.end == 1.5
        assert hrc3.start == 1.5
        assert hrc3.end == 3

    def test_increase_level(self, tl, cm):
        hrc = tl.create_hierarchy(0, 1, 1)
        cm.change_level(hrc, 1)
        assert hrc.level == 2

    def test_decrease_level(self, tl, cm):
        hrc = tl.create_hierarchy(0, 1, 2)
        cm.change_level(hrc, -1)
        assert hrc.level == 1

    def test_decrease_level_below_one_raises_error(self, tl, cm):
        hrc = tl.create_hierarchy(0, 1, 1)
        with pytest.raises(HierarchyOperationError):
            cm.change_level(hrc, -1)

        with pytest.raises(HierarchyOperationError):
            cm.change_level(hrc, -2)

    def test_do_genealogy_empty_timeline(self, tl):
        tl.do_genealogy()

    def test_do_genealogy_single_hierarchy(self, tl):
        hrc = tl.create_hierarchy(0, 1, 1)

        tl.do_genealogy()

        assert not hrc.parent
        assert not hrc.children

    def test_do_genealogy_unrelated_hierarchies(self, tl):
        first = tl.create_hierarchy(0, 1, 1)
        second = tl.create_hierarchy(1, 2, 1)

        tl.do_genealogy()

        assert not first.parent
        assert not second.parent
        assert not first.children
        assert not second.children

    def test_do_genealogy_simple_parent_child(self, tl):
        parent = tl.create_hierarchy(0, 1, 2)
        child = tl.create_hierarchy(0, 1, 1)

        tl.do_genealogy()

        assert set(parent.children) == {child}
        assert child.parent == parent
        assert child.children == []

    def test_do_genealogy_empty_space_after_child(self, tl):
        parent = tl.create_hierarchy(0, 2, 2)
        child = tl.create_hierarchy(0, 1, 1)

        tl.do_genealogy()

        assert set(parent.children) == {child}
        assert child.parent == parent
        assert child.children == []

    def test_do_genealogy_parent_two_levels_up(self, tl):
        parent = tl.create_hierarchy(0, 1, 3)
        child = tl.create_hierarchy(0, 1, 1)

        tl.do_genealogy()

        assert set(parent.children) == {child}
        assert child.parent == parent
        assert child.children == []

    def test_do_genealogy_two_children(self, tl):
        parent = tl.create_hierarchy(0, 2, 2)
        child1 = tl.create_hierarchy(0, 1, 1)
        child2 = tl.create_hierarchy(1, 2, 1)

        tl.do_genealogy()

        assert set(parent.children) == {child1, child2}
        assert child1.parent == parent
        assert child2.parent == parent
        assert child1.children == []
        assert child2.children == []

    def test_do_genealogy_nested_single_children(self, tl):
        top = tl.create_hierarchy(0, 1, 3)
        mid = tl.create_hierarchy(0, 1, 2)
        bot = tl.create_hierarchy(0, 1, 1)

        tl.do_genealogy()

        assert bot.parent == mid
        assert mid.parent == top
        assert set(top.children) == {mid}
        assert set(mid.children) == {bot}
        assert bot.children == []

    def test_do_genealogy_nested_two_sets_of_children(self, tl):
        """
                top
               /   \
             mid1 mid2
              |    |
            bot1  bot2
        """
        top = tl.create_hierarchy(0, 2, 3)
        mid1 = tl.create_hierarchy(0, 1, 2)
        bot1 = tl.create_hierarchy(0, 1, 1)
        mid2 = tl.create_hierarchy(1, 2, 2)
        bot2 = tl.create_hierarchy(1, 2, 1)

        tl.do_genealogy()

        assert bot1.parent == mid1
        assert bot2.parent == mid2
        assert mid1.parent == top
        assert mid2.parent == top
        assert set(top.children) == {mid1, mid2}
        assert set(mid1.children) == {bot1}
        assert set(mid2.children) == {bot2}
        assert bot1.children == []
        assert bot2.children == []

    def test_do_genealogy_parent_child_pairs_with_no_common_parent(self, tl):
        parent1 = tl.create_hierarchy(0, 1, 2)
        parent2 = tl.create_hierarchy(1, 2, 2)
        child1 = tl.create_hierarchy(0, 1, 1)
        child2 = tl.create_hierarchy(1, 2, 1)

        tl.do_genealogy()

        assert parent1.children == [child1]
        assert parent1.parent is None
        assert child1.parent == parent1
        assert child1.children == []

        assert parent2.children == [child2]
        assert parent2.parent is None
        assert child2.parent == parent2
        assert child2.children == []

    def test_get_boundary_conflicts_empty_timeline(self, tl):
        assert not tl.get_boundary_conflicts()

    def test_get_boundary_conflicts_one_hierarchy(self, tl):
        tl.create_hierarchy(0, 1, 1)
        assert not tl.get_boundary_conflicts()

    def test_get_boundary_conflicts_duplicate_hierarchy(self, tl):
        h1 = tl.create_hierarchy(0, 1, 1)
        h2 = tl.create_hierarchy(0, 1, 1)

        assert set(tl.get_boundary_conflicts()[0]) == {h1, h2}

    def test_get_boundary_conflicts_separate_hierarchies(self, tl):
        tl.create_hierarchy(0, 1, 1)
        tl.create_hierarchy(2, 3, 1)
        assert not tl.get_boundary_conflicts()

    def test_get_boundary_conflicts_adjacent_hierarchies(self, tl):
        tl.create_hierarchy(0, 1, 1)
        tl.create_hierarchy(1, 2, 1)
        tl.create_hierarchy(2, 3, 1)
        assert not tl.get_boundary_conflicts()

    def test_get_boundary_conflicts_parent_and_child(self, tl):
        tl.create_hierarchy(0, 1, 2)
        tl.create_hierarchy(0, 1, 1)
        assert not tl.get_boundary_conflicts()

    def test_get_boundary_conflicts_parent_and_child_boundaries_do_not_coincide(
        self, tl
    ):
        tl.create_hierarchy(0, 3, 2)
        tl.create_hierarchy(1, 2, 1)
        assert not tl.get_boundary_conflicts()

    def test_get_boundary_conflicts_parent_and_children(self, tl):
        tl.create_hierarchy(0, 2, 2)
        tl.create_hierarchy(0, 1, 1)
        tl.create_hierarchy(1, 2, 1)
        assert not tl.get_boundary_conflicts()

    def test_get_boundary_conflicts_parent_and_nested_children(self, tl):
        tl.create_hierarchy(0, 1, 1)
        tl.create_hierarchy(0, 1, 2)
        tl.create_hierarchy(0, 1, 3)
        assert not tl.get_boundary_conflicts()

    def test_get_boundary_conflicts_end_crosses_on_same_level(self, tl):
        h1 = tl.create_hierarchy(1, 3, 1)
        h2 = tl.create_hierarchy(0, 2, 1)
        assert set(tl.get_boundary_conflicts()[0]) == {h1, h2}

    def test_get_boundary_conflicts_end_crosses_on_higher_level(self, tl):
        h1 = tl.create_hierarchy(1, 3, 1)
        h2 = tl.create_hierarchy(0, 2, 2)
        assert set(tl.get_boundary_conflicts()[0]) == {h1, h2}

    def test_get_boundary_conflicts_end_crosses_on_lower_level(self, tl):
        h1 = tl.create_hierarchy(1, 3, 2)
        h2 = tl.create_hierarchy(0, 2, 1)
        assert set(tl.get_boundary_conflicts()[0]) == {h1, h2}

    def test_get_boundary_conflicts_start_crosses_on_same_level(self, tl):
        h1 = tl.create_hierarchy(0, 2, 1)
        h2 = tl.create_hierarchy(1, 3, 1)
        assert set(tl.get_boundary_conflicts()[0]) == {h1, h2}

    def test_get_boundary_conflicts_start_crosses_on_higher_level(self, tl):
        h1 = tl.create_hierarchy(0, 2, 1)
        h2 = tl.create_hierarchy(1, 3, 2)
        assert set(tl.get_boundary_conflicts()[0]) == {h1, h2}

    def test_get_boundary_conflicts_start_crosses_on_lower_level(self, tl):
        h1 = tl.create_hierarchy(0, 2, 2)
        h2 = tl.create_hierarchy(1, 3, 1)
        assert set(tl.get_boundary_conflicts()[0]) == {h1, h2}

    def test_get_boundary_conflicts_crosses_multiple_on_same_level(self, tl):
        h1 = tl.create_hierarchy(1, 2, 1)
        h2 = tl.create_hierarchy(2, 3, 1)
        h3 = tl.create_hierarchy(0, 4, 1)
        conflicts = [set(c) for c in tl.get_boundary_conflicts()]
        assert len(conflicts) == 2
        assert {h1, h3} in conflicts
        assert {h2, h3} in conflicts

    def test_get_boundary_conflicts_crosses_multiple_on_different_levels(self, tl):
        h1 = tl.create_hierarchy(1, 2, 2)
        h2 = tl.create_hierarchy(2, 3, 3)
        h3 = tl.create_hierarchy(0, 4, 1)
        conflicts = [set(c) for c in tl.get_boundary_conflicts()]
        assert len(conflicts) == 2
        assert {h1, h3} in conflicts
        assert {h2, h3} in conflicts

    def test_get_boundary_conflicts_three_mutual_conflicts(self, tl):
        h1 = tl.create_hierarchy(0, 1, 1)
        h2 = tl.create_hierarchy(0, 1, 1)
        h3 = tl.create_hierarchy(0, 1, 1)
        conflicts = [set(c) for c in tl.get_boundary_conflicts()]
        assert len(conflicts) == 3
        assert {h1, h2} in conflicts
        assert {h1, h3} in conflicts
        assert {h2, h3} in conflicts
