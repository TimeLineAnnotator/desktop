import itertools

import pytest

from tilia.exceptions import InvalidComponentKindError
from tilia.timelines.hierarchy.components import Hierarchy
from tilia.timelines.hierarchy.timeline import (
    HierarchyTLComponentManager,
)


class DummyTimelines:
    ID_ITER = itertools.count()

    def get_id(self):
        return next(self.ID_ITER)

    @staticmethod
    def get_media_length():
        return 100


@pytest.fixture
def cm(hierarchy_tl) -> HierarchyTLComponentManager:
    return hierarchy_tl.component_manager


class TestHierarchyTimeline:
    # TEST CREATE
    def test_create_hierarchy(self, hierarchy_tl):
        hierarchy_tl.create_hierarchy(start=0, end=1, level=1)

        assert len(hierarchy_tl) == 1

    def test_create_duplicate_fails(self, hierarchy_tl):
        hierarchy_tl.create_hierarchy(start=0, end=1, level=1)
        hierarchy_tl.create_hierarchy(start=0, end=1, level=1)

        assert len(hierarchy_tl) == 1


class TestHierarchyTimelineComponentManager:
    def test_create_invalid_component_kind_raises_error(self, hierarchy_tl):
        with pytest.raises(InvalidComponentKindError):
            # noinspection PyTypeChecker
            hierarchy_tl.component_manager.create_component(
                "INVALID KIND", None, 0, 1, 1
            )

    def test_create_unit_below(self, hierarchy_tl):
        parent, _ = hierarchy_tl.create_hierarchy(start=0, end=1, level=3)
        child, _ = hierarchy_tl.create_hierarchy(start=0, end=1, level=1)

        hierarchy_tl.component_manager.create_child(parent)

        assert child.parent in parent.children

    # TEST CLEAR
    def test_clear(self, hierarchy_tl):
        hierarchy_tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=2)
        hierarchy_tl.create_hierarchy(start=0.2, end=0.3, level=3)

        hierarchy_tl.component_manager.clear()

        assert not hierarchy_tl.component_manager._components

    # TEST MERGE
    def test_merge_two_units_without_units_between(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.5, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.5, end=1, level=1)

        hierarchy_tl.component_manager.merge([hrc1, hrc2])

        assert len(hierarchy_tl) == 1

    def test_merge_two_units_with_units_in_between(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hierarchy_tl.create_hierarchy(start=0.2, end=0.3, level=1)
        hrc4, _ = hierarchy_tl.create_hierarchy(start=0.3, end=0.4, level=1)

        hierarchy_tl.component_manager.merge([hrc1, hrc4])

        assert len(hierarchy_tl) == 1

    def test_merge_three_units(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hrc3, _ = hierarchy_tl.create_hierarchy(start=0.2, end=0.3, level=1)

        hierarchy_tl.component_manager.merge([hrc1, hrc2, hrc3])

        assert len(hierarchy_tl) == 1

    def test_merge_four_units(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hrc3, _ = hierarchy_tl.create_hierarchy(start=0.2, end=0.3, level=1)
        hrc4, _ = hierarchy_tl.create_hierarchy(start=0.3, end=0.4, level=1)

        hierarchy_tl.component_manager.merge([hrc1, hrc2, hrc3, hrc4])

        assert len(hierarchy_tl) == 1

    def test_merge_two_units_with_children(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.5, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.5, level=2)
        hrc3, _ = hierarchy_tl.create_hierarchy(start=0.5, end=1.0, level=1)
        hrc4, _ = hierarchy_tl.create_hierarchy(start=0.5, end=1.0, level=2)

        hierarchy_tl.component_manager.merge([hrc2, hrc4])

        assert hrc1.parent == hrc3.parent

    def test_merge_two_units_with_common_parent(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.5, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.5, end=1, level=1)
        hrc3, _ = hierarchy_tl.create_hierarchy(start=0.0, end=1, level=2)

        hierarchy_tl.component_manager.merge([hrc1, hrc2])

        assert len(hrc3.children) == 1
        assert hrc1 not in hrc3.children
        assert hrc2 not in hrc3.children

    def test_merge_two_units_with_unit_with_children_in_between(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.1, level=2)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=2)
        hrc3, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hrc4, _ = hierarchy_tl.create_hierarchy(start=0.2, end=0.3, level=2)

        hierarchy_tl.component_manager.merge([hrc1, hrc4])

        assert len(hierarchy_tl) == 2
        assert hrc3.parent.start == 0.0 and hrc3.parent.end == 0.3

    def test_merge_one_unit_raises_error(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.1, level=1)

        success, _ = hierarchy_tl.component_manager.merge([hrc1])

    def test_merge_units_of_different_level_raises_error(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=2)

        success, _ = hierarchy_tl.component_manager.merge([hrc1, hrc2])

    def test_merge_with_unit_of_different_level_in_between_raises_error(
        self, hierarchy_tl
    ):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=2)
        hrc3, _ = hierarchy_tl.create_hierarchy(start=0.2, end=0.3, level=1)

        success, _ = hierarchy_tl.component_manager.merge([hrc1, hrc3])

    def test_merge_with_different_parent_raises_error(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hrc3, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=2)

        success, _ = hierarchy_tl.component_manager.merge([hrc1, hrc3])

    # TEST SERIALIZE
    # noinspection PyUnresolvedReferences
    def test_serialize_components(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=2)
        hrc3, _ = hierarchy_tl.create_hierarchy(start=0.2, end=0.3, level=3)

        serialized_components = hierarchy_tl.component_manager.serialize_components()

        for unit in [hrc1, hrc2, hrc3]:
            assert serialized_components[unit.id]["start"] == unit.start
            assert serialized_components[unit.id]["end"] == unit.end
            assert serialized_components[unit.id]["level"] == unit.level

    # noinspection PyUnresolvedReferences
    def test_deserialize_components(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=2)
        hrc3, _ = hierarchy_tl.create_hierarchy(start=0.2, end=0.3, level=3)

        serialized_components = hierarchy_tl.component_manager.serialize_components()

        hierarchy_tl.component_manager.clear()

        hierarchy_tl.component_manager.deserialize_components(serialized_components)

        assert len(hierarchy_tl) == 3
        assert {dsu.start for dsu in hierarchy_tl.component_manager._components} == {
            u.start for u in [hrc1, hrc2, hrc3]
        }
        assert {dsu.end for dsu in hierarchy_tl.component_manager._components} == {
            u.end for u in [hrc1, hrc2, hrc3]
        }
        assert {dsu.level for dsu in hierarchy_tl.component_manager._components} == {
            u.level for u in [hrc1, hrc2, hrc3]
        }

    def test_deserialize_components_with_children(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0, end=1, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=1, end=2, level=2)
        hrc3, _ = hierarchy_tl.create_hierarchy(start=0, end=2, level=3)

        serialized_components = hierarchy_tl.component_manager.serialize_components()

        hierarchy_tl.clear()

        hierarchy_tl.component_manager.deserialize_components(serialized_components)

        dsrl_hrc1, dsrl_hrc2, dsrl_hrc3 = sorted(
            list(hierarchy_tl.component_manager._components), key=lambda x: x.level
        )

        assert dsrl_hrc1 in dsrl_hrc3.children
        assert dsrl_hrc2 in dsrl_hrc3.children
        assert dsrl_hrc1.parent == dsrl_hrc3
        assert dsrl_hrc2.parent == dsrl_hrc3

        hierarchy_tl.clear()

    # TEST CROP
    def test_crop(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.3, level=1)

        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=2)

        hierarchy_tl.create_hierarchy(start=0.2, end=0.3, level=3)

        hrc4, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.1, level=1)

        hierarchy_tl.component_manager.crop(0.15)

        assert len(hierarchy_tl) == 3
        assert hrc1.start == 0.0
        assert hrc1.end == 0.15
        assert hrc2.start == 0.1
        assert hrc2.end == 0.15
        assert hrc4.start == 0.0
        assert hrc4.end == 0.1

    def test_scale(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0, end=1, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=1, end=3, level=2)
        hrc3, _ = hierarchy_tl.create_hierarchy(start=3, end=6, level=3)

        hierarchy_tl.component_manager.scale(0.5)

        assert len(hierarchy_tl) == 3
        assert hrc1.start == 0
        assert hrc1.end == 0.5
        assert hrc2.start == 0.5
        assert hrc2.end == 1.5
        assert hrc3.start == 1.5
        assert hrc3.end == 3

    def test_increase_level(self, hierarchy_tl):
        hrc, _ = hierarchy_tl.create_hierarchy(0, 1, 1)
        hierarchy_tl.alter_levels([hrc], 1)
        assert hrc.level == 2

    def test_decrease_level(self, hierarchy_tl):
        hrc, _ = hierarchy_tl.create_hierarchy(0, 1, 2)
        hierarchy_tl.alter_levels([hrc], -1)
        assert hrc.level == 1

    def test_decrease_level_below_one_fails(self, hierarchy_tl):
        hrc, _ = hierarchy_tl.create_hierarchy(0, 1, 1)
        hierarchy_tl.alter_levels([hrc], -1)
        assert hrc.level == 1

        hierarchy_tl.alter_levels([hrc], -10)
        assert hrc.level == 1

    def test_genealogy_single_hierarchy(self, hierarchy_tl):
        hrc, _ = hierarchy_tl.create_hierarchy(0, 1, 1)

        assert not hrc.parent
        assert not hrc.children

    def test_genealogy_unrelated_hierarchies(self, hierarchy_tl):
        first, _ = hierarchy_tl.create_hierarchy(0, 1, 1)
        second, _ = hierarchy_tl.create_hierarchy(1, 2, 1)

        assert not first.parent
        assert not second.parent
        assert not first.children
        assert not second.children

    def test_genealogy_simple_parent_child(self, hierarchy_tl):
        parent, _ = hierarchy_tl.create_hierarchy(0, 1, 2)
        child, _ = hierarchy_tl.create_hierarchy(0, 1, 1)

        assert set(parent.children) == {child}
        assert child.parent == parent
        assert child.children == []

    def test_genealogy_empty_space_after_child(self, hierarchy_tl):
        parent, _ = hierarchy_tl.create_hierarchy(0, 2, 2)
        child, _ = hierarchy_tl.create_hierarchy(0, 1, 1)

        assert set(parent.children) == {child}
        assert child.parent == parent
        assert child.children == []

    def test_genealogy_parent_two_levels_up(self, hierarchy_tl):
        parent, _ = hierarchy_tl.create_hierarchy(0, 1, 3)
        child, _ = hierarchy_tl.create_hierarchy(0, 1, 1)

        assert set(parent.children) == {child}
        assert child.parent == parent
        assert child.children == []

    def test_genealogy_two_children(self, hierarchy_tl):
        parent, _ = hierarchy_tl.create_hierarchy(0, 2, 2)
        child1, _ = hierarchy_tl.create_hierarchy(0, 1, 1)
        child2, _ = hierarchy_tl.create_hierarchy(1, 2, 1)

        assert set(parent.children) == {child1, child2}
        assert child1.parent == parent
        assert child2.parent == parent
        assert child1.children == []
        assert child2.children == []

    def test_genealogy_nested_single_children(self, hierarchy_tl):
        """
        top
         |
        mid
         |
        bot
        """
        top, _ = hierarchy_tl.create_hierarchy(0, 1, 3)
        mid, _ = hierarchy_tl.create_hierarchy(0, 1, 2)
        bot, _ = hierarchy_tl.create_hierarchy(0, 1, 1)

        assert bot.parent == mid
        assert mid.parent == top
        assert set(top.children) == {mid}
        assert set(mid.children) == {bot}
        assert bot.children == []

    def test_genealogy_nested_two_sets_of_children(self, hierarchy_tl):
        """
                top
               /   \
             mid1 mid2
              |    |
            bot1  bot2
        """
        top, _ = hierarchy_tl.create_hierarchy(0, 2, 3)
        mid1, _ = hierarchy_tl.create_hierarchy(0, 1, 2)
        bot1, _ = hierarchy_tl.create_hierarchy(0, 1, 1)
        mid2, _ = hierarchy_tl.create_hierarchy(1, 2, 2)
        bot2, _ = hierarchy_tl.create_hierarchy(1, 2, 1)

        assert bot1.parent == mid1
        assert bot2.parent == mid2
        assert mid1.parent == top
        assert mid2.parent == top
        assert set(top.children) == {mid1, mid2}
        assert set(mid1.children) == {bot1}
        assert set(mid2.children) == {bot2}
        assert bot1.children == []
        assert bot2.children == []

    def test_genealogy_parent_child_pairs_with_no_common_parent(self, hierarchy_tl):
        parent1, _ = hierarchy_tl.create_hierarchy(0, 1, 2)
        parent2, _ = hierarchy_tl.create_hierarchy(1, 2, 2)
        child1, _ = hierarchy_tl.create_hierarchy(0, 1, 1)
        child2, _ = hierarchy_tl.create_hierarchy(1, 2, 1)

        assert parent1.children == [child1]
        assert parent1.parent is None
        assert child1.parent == parent1
        assert child1.children == []

        assert parent2.children == [child2]
        assert parent2.parent is None
        assert child2.parent == parent2
        assert child2.children == []

    def test_get_boundary_conflicts_empty_timeline(self, hierarchy_tl):
        assert not hierarchy_tl.get_boundary_conflicts()

    def test_get_boundary_conflicts_one_hierarchy(self, hierarchy_tl):
        hierarchy_tl.create_hierarchy(0, 1, 1)
        assert not hierarchy_tl.get_boundary_conflicts()

    def test_get_boundary_conflicts_separate_hierarchies(self, hierarchy_tl):
        hierarchy_tl.create_hierarchy(0, 1, 1)
        hierarchy_tl.create_hierarchy(2, 3, 1)
        assert not hierarchy_tl.get_boundary_conflicts()

    def test_get_boundary_conflicts_adjacent_hierarchies(self, hierarchy_tl):
        hierarchy_tl.create_hierarchy(0, 1, 1)
        hierarchy_tl.create_hierarchy(1, 2, 1)
        hierarchy_tl.create_hierarchy(2, 3, 1)
        assert not hierarchy_tl.get_boundary_conflicts()

    def test_get_boundary_conflicts_parent_and_child(self, hierarchy_tl):
        hierarchy_tl.create_hierarchy(0, 1, 2)
        hierarchy_tl.create_hierarchy(0, 1, 1)
        assert not hierarchy_tl.get_boundary_conflicts()

    def test_get_boundary_conflicts_parent_and_child_boundaries_do_not_coincide(
        self, hierarchy_tl
    ):
        hierarchy_tl.create_hierarchy(0, 3, 2)
        hierarchy_tl.create_hierarchy(1, 2, 1)
        assert not hierarchy_tl.get_boundary_conflicts()

    def test_get_boundary_conflicts_parent_and_children(self, hierarchy_tl):
        hierarchy_tl.create_hierarchy(0, 2, 2)
        hierarchy_tl.create_hierarchy(0, 1, 1)
        hierarchy_tl.create_hierarchy(1, 2, 1)
        assert not hierarchy_tl.get_boundary_conflicts()

    def test_get_boundary_conflicts_parent_and_nested_children(self, hierarchy_tl):
        hierarchy_tl.create_hierarchy(0, 1, 1)
        hierarchy_tl.create_hierarchy(0, 1, 2)
        hierarchy_tl.create_hierarchy(0, 1, 3)
        assert not hierarchy_tl.get_boundary_conflicts()

    def test_get_boundary_conflicts_end_crosses_on_same_level(self, hierarchy_tl):
        h1, _ = hierarchy_tl.create_hierarchy(1, 3, 1)
        h2, _ = hierarchy_tl.create_hierarchy(0, 2, 1)
        assert set(hierarchy_tl.get_boundary_conflicts()[0]) == {h1, h2}

    def test_get_boundary_conflicts_end_crosses_on_higher_level(self, hierarchy_tl):
        h1, _ = hierarchy_tl.create_hierarchy(1, 3, 1)
        h2, _ = hierarchy_tl.create_hierarchy(0, 2, 2)
        assert set(hierarchy_tl.get_boundary_conflicts()[0]) == {h1, h2}

    def test_get_boundary_conflicts_end_crosses_on_lower_level(self, hierarchy_tl):
        h1, _ = hierarchy_tl.create_hierarchy(1, 3, 2)
        h2, _ = hierarchy_tl.create_hierarchy(0, 2, 1)
        assert set(hierarchy_tl.get_boundary_conflicts()[0]) == {h1, h2}

    def test_get_boundary_conflicts_start_crosses_on_same_level(self, hierarchy_tl):
        h1, _ = hierarchy_tl.create_hierarchy(0, 2, 1)
        h2, _ = hierarchy_tl.create_hierarchy(1, 3, 1)
        assert set(hierarchy_tl.get_boundary_conflicts()[0]) == {h1, h2}

    def test_get_boundary_conflicts_start_crosses_on_higher_level(self, hierarchy_tl):
        h1, _ = hierarchy_tl.create_hierarchy(0, 2, 1)
        h2, _ = hierarchy_tl.create_hierarchy(1, 3, 2)
        assert set(hierarchy_tl.get_boundary_conflicts()[0]) == {h1, h2}

    def test_get_boundary_conflicts_start_crosses_on_lower_level(self, hierarchy_tl):
        h1, _ = hierarchy_tl.create_hierarchy(0, 2, 2)
        h2, _ = hierarchy_tl.create_hierarchy(1, 3, 1)
        assert set(hierarchy_tl.get_boundary_conflicts()[0]) == {h1, h2}

    def test_get_boundary_conflicts_crosses_multiple_on_same_level(self, hierarchy_tl):
        h1, _ = hierarchy_tl.create_hierarchy(1, 2, 1)
        h2, _ = hierarchy_tl.create_hierarchy(2, 3, 1)
        h3, _ = hierarchy_tl.create_hierarchy(0, 4, 1)
        conflicts = [set(c) for c in hierarchy_tl.get_boundary_conflicts()]
        assert len(conflicts) == 2
        assert {h1, h3} in conflicts
        assert {h2, h3} in conflicts

    def test_get_boundary_conflicts_crosses_multiple_on_different_levels(
        self, hierarchy_tl
    ):
        h1, _ = hierarchy_tl.create_hierarchy(1, 2, 2)
        h2, _ = hierarchy_tl.create_hierarchy(2, 3, 3)
        h3, _ = hierarchy_tl.create_hierarchy(0, 4, 1)
        conflicts = [set(c) for c in hierarchy_tl.get_boundary_conflicts()]
        assert len(conflicts) == 2
        assert {h1, h3} in conflicts
        assert {h2, h3} in conflicts


class TestSplit:
    # TEST SPLIT
    def test_get_unit_for_split_from_single_unit(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=1, level=1)
        unit_for_split = hierarchy_tl.component_manager.get_unit_to_split(0.5)

        assert unit_for_split == hrc1

    def test_get_unit_for_split_from_unit_boundary(self, hierarchy_tl):
        hierarchy_tl.create_hierarchy(start=0.0, end=0.5, level=1)
        hierarchy_tl.create_hierarchy(start=0.5, end=1, level=1)

        unit_for_split = hierarchy_tl.component_manager.get_unit_to_split(0.5)

        assert unit_for_split is None

    def test_get_unit_for_split_from_units_of_different_levels_spanning_time(
        self, hierarchy_tl
    ):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=1, level=1)
        hierarchy_tl.create_hierarchy(start=0.0, end=1, level=2)
        hierarchy_tl.create_hierarchy(start=0.0, end=1, level=3)

        unit_for_split = hierarchy_tl.component_manager.get_unit_to_split(0.5)

        assert unit_for_split is hrc1

    def test_split_unit_without_parent(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=1, level=1)

        hierarchy_tl.component_manager.split(hrc1, 0.5)

        assert hrc1 not in hierarchy_tl.component_manager._components
        assert len(hierarchy_tl) == 2

    def test_split_unit_with_parent(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=1, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.0, end=1, level=2)

        hierarchy_tl.component_manager.split(hrc1, 0.5)

        assert hrc1 not in hierarchy_tl.component_manager._components
        assert hrc1 not in hrc2.children
        assert len(hierarchy_tl) == 3
        assert len(hrc2.children) == 2

    def test_split_unit_passes_comments(self, hierarchy_tl):
        """Comments should be inherited by both resulting units"""
        hierarchy_tl.create_hierarchy(start=0.0, end=1, level=1, comments="inherit me")

        hierarchy_tl.split(0.5)

        assert hierarchy_tl[0].comments == "inherit me"
        assert hierarchy_tl[1].comments == "inherit me"

    def test_split_unit_passes_pre_start(self, hierarchy_tl):
        """Pre-start should be inherited only by the left unit"""
        hierarchy_tl.create_hierarchy(
            pre_start=0,
            start=0.2,
            end=1,
            level=1,
        )

        hierarchy_tl.split(0.5)

        assert hierarchy_tl[0].pre_start == 0
        assert hierarchy_tl[1].pre_start == 0.5

    def test_split_unit_passes_post_end(self, hierarchy_tl):
        """Pre-start should be inherited only by the left unit"""
        hierarchy_tl.create_hierarchy(
            post_end=1,
            start=0,
            end=0.9,
            level=1,
        )

        hierarchy_tl.split(0.5)

        assert hierarchy_tl[0].post_end == 0.5
        assert hierarchy_tl[1].post_end == 1

    def test_split_unit_with_children(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.5, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.5, end=1, level=1)
        hrc3, _ = hierarchy_tl.create_hierarchy(start=0, end=1, level=2)

        hierarchy_tl.component_manager.split(hrc3, 0.5)

        assert len(hierarchy_tl) == 4
        assert hrc1.parent
        assert hrc2.parent
        assert hrc1.parent != hrc2.parent


class TestGroup:
    def test_single_unit(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0, end=0.1, level=1)
        success, _ = hierarchy_tl.component_manager.group([hrc1])
        hrc2 = hierarchy_tl[1]

        assert success
        assert len(hierarchy_tl) == 2
        assert hrc2.level == 2
        assert hrc1.parent == hrc2
        assert hrc2.children == [hrc1]

    def test_group_two_units(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0, end=0.1, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=1)

        hierarchy_tl.component_manager.group([hrc1, hrc2])

        assert hrc1.parent == hrc2.parent
        assert hrc1.parent.level == 2

    def test_two_units_out_of_order(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0, end=0.1, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=1)

        hierarchy_tl.component_manager.group([hrc2, hrc1])

        assert hrc1.parent == hrc2.parent

    def test_two_units_with_units_of_same_level_in_between(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0, end=0.1, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hrc3, _ = hierarchy_tl.create_hierarchy(start=0.2, end=0.3, level=1)
        hrc4, _ = hierarchy_tl.create_hierarchy(start=0.3, end=0.4, level=1)

        hierarchy_tl.component_manager.group([hrc1, hrc4])

        assert hrc1.parent == hrc2.parent == hrc3.parent == hrc4.parent

    def test_two_units_with_unit_with_children_in_between(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0, end=0.1, level=2)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hrc3, _ = hierarchy_tl.create_hierarchy(start=0.2, end=0.3, level=1)
        hrc4, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.3, level=2)
        hrc5, _ = hierarchy_tl.create_hierarchy(start=0.3, end=0.4, level=2)

        hierarchy_tl.component_manager.group([hrc1, hrc5])

        assert hrc1.parent == hrc4.parent == hrc5.parent

    def test_three_units_with_units_between_grouped_units(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0, end=0.1, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hrc3, _ = hierarchy_tl.create_hierarchy(start=0.2, end=0.3, level=1)
        hrc4, _ = hierarchy_tl.create_hierarchy(start=0.3, end=0.4, level=1)
        hrc5, _ = hierarchy_tl.create_hierarchy(start=0.4, end=0.5, level=1)

        hierarchy_tl.component_manager.group([hrc1, hrc3, hrc5])

        assert hrc1.parent == hrc2.parent == hrc3.parent == hrc4.parent

    def test_two_units_with_parent_two_levels_higher(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hrc3, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.2, level=3)

        hierarchy_tl.component_manager.group([hrc1, hrc2])

        assert hrc1.parent == hrc2.parent
        assert not hrc1.parent == hrc3 or hrc2.parent == hrc3
        assert hrc1.parent in hrc3.children

    def test_two_units_with_parent_that_has_parent(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.4, level=4)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.4, level=3)
        hrc3, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc4, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hrc5, _ = hierarchy_tl.create_hierarchy(start=0.2, end=0.3, level=1)
        hrc6, _ = hierarchy_tl.create_hierarchy(start=0.3, end=0.4, level=1)

        hierarchy_tl.component_manager.group([hrc3, hrc4])

        assert hrc3.parent == hrc4.parent
        assert hrc3.parent.parent == hrc2
        assert hrc5.parent == hrc2
        assert hrc6.parent == hrc2
        assert hrc3.parent in hrc2.children
        assert hrc5 in hrc2.children
        assert hrc6 in hrc2.children

    def test_two_units_with_units_of_higher_level_in_between_fails(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0, end=0.1, level=1)
        _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=2)
        _ = hierarchy_tl.create_hierarchy(start=0.2, end=0.3, level=3)
        hrc4, _ = hierarchy_tl.create_hierarchy(start=0.3, end=0.4, level=1)

        success, _ = hierarchy_tl.component_manager.group([hrc1, hrc4])
        assert not success

    def test_empty_list_fails(self, hierarchy_tl):
        success, _ = hierarchy_tl.component_manager.group([])
        assert not success

    def test_crossing_end_boundary_fails(self, hierarchy_tl):
        hierarchy_tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hierarchy_tl.create_hierarchy(start=0.0, end=0.2, level=2)
        hrc4, _ = hierarchy_tl.create_hierarchy(start=0.2, end=0.3, level=1)

        success, _ = hierarchy_tl.component_manager.group([hrc2, hrc4])
        assert not success

    def test_crossing_start_boundary_fails(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hierarchy_tl.create_hierarchy(start=0.2, end=0.3, level=1)
        hierarchy_tl.create_hierarchy(start=0.1, end=0.3, level=2)

        success, _ = hierarchy_tl.component_manager.group([hrc1, hrc2])
        assert not success

    def test_overlapping_with_higher_unit_fails(self, hierarchy_tl):
        hrc1, _ = hierarchy_tl.create_hierarchy(start=0.0, end=0.1, level=1)
        hrc2, _ = hierarchy_tl.create_hierarchy(start=0.1, end=0.2, level=1)
        hierarchy_tl.create_hierarchy(start=0.0, end=0.2, level=2)

        success, _ = hierarchy_tl.component_manager.group([hrc1, hrc2])
        assert not success


class TestMerge:
    ATTRS = ("label", "comments")

    @staticmethod
    def create_units_to_merge(hierarchy_tl, count: int = 2) -> list[Hierarchy]:
        hierarchies = []
        for i in range(count):
            hrc, _ = hierarchy_tl.create_hierarchy(start=i, end=i + 1, level=1)
            hierarchies.append(hrc)

        return hierarchies

    @staticmethod
    def set_attr(hierarchy: Hierarchy, attr_name: str, value: str) -> None:
        hierarchy.set_data(attr_name, value)

    @staticmethod
    def get_attr(hierarchy: Hierarchy, attr_name: str) -> str | None:
        return hierarchy.get_data(attr_name)

    @pytest.mark.parametrize("attr_name", ATTRS)
    def test_preserves_left_when_right_is_empty(self, hierarchy_tl, attr_name):
        hrcs = self.create_units_to_merge(hierarchy_tl, 2)
        self.set_attr(hrcs[0], attr_name, "left")

        hierarchy_tl.merge(hrcs)

        assert self.get_attr(hierarchy_tl[0], attr_name) == "left"

    @pytest.mark.parametrize("attr_name", ATTRS)
    def test_preserves_right_when_left_is_empty(self, hierarchy_tl, attr_name):
        hrcs = self.create_units_to_merge(hierarchy_tl, 2)
        self.set_attr(hrcs[1], attr_name, "right")

        hierarchy_tl.merge(hrcs)

        assert self.get_attr(hierarchy_tl[0], attr_name) == "right"

    @pytest.mark.parametrize("attr_name", ATTRS)
    def test_preserves_middle_when_neighbours_are_empty(self, hierarchy_tl, attr_name):
        hrcs = self.create_units_to_merge(hierarchy_tl, 3)
        self.set_attr(hrcs[1], attr_name, "middle")

        hierarchy_tl.merge(hrcs)

        assert self.get_attr(hierarchy_tl[0], attr_name) == "middle"

    @pytest.mark.parametrize("attr_name", ATTRS)
    def test_concatenates_when_both_units_have_it(self, hierarchy_tl, attr_name):
        hrcs = self.create_units_to_merge(hierarchy_tl, 2)
        self.set_attr(hrcs[0], attr_name, "left")
        self.set_attr(hrcs[1], attr_name, "right")

        hierarchy_tl.merge(hrcs)

        new_value = self.get_attr(hierarchy_tl[0], attr_name)
        assert new_value == "left" + hierarchy_tl.merge_separator + "right"

    @pytest.mark.parametrize("attr_name", ATTRS)
    def test_concatenates_more_than_two(self, hierarchy_tl, attr_name):
        hrcs = self.create_units_to_merge(hierarchy_tl, 4)
        values = ["one", "two", "three", "four"]
        for i, value in enumerate(values):
            self.set_attr(hrcs[i], attr_name, value)

        hierarchy_tl.merge(hrcs)

        new_value = self.get_attr(hierarchy_tl[0], attr_name)
        assert new_value == hierarchy_tl.merge_separator.join(values)

    @pytest.mark.parametrize("attr_name", ATTRS)
    def test_ignores_empty_when_concatenating(self, hierarchy_tl, attr_name):
        hrcs = self.create_units_to_merge(hierarchy_tl, 5)
        self.set_attr(hrcs[1], attr_name, "first")
        self.set_attr(hrcs[3], attr_name, "second")

        hierarchy_tl.merge(hrcs)

        new_value = self.get_attr(hierarchy_tl[0], attr_name)
        assert new_value == "first" + hierarchy_tl.merge_separator + "second"

    @pytest.mark.parametrize("attr_name", ATTRS)
    def test_identical_values_kept_without_separator(self, hierarchy_tl, attr_name):
        hrcs = self.create_units_to_merge(hierarchy_tl, 3)
        for h in hrcs:
            self.set_attr(h, attr_name, "same")

        hierarchy_tl.merge(hrcs)

        assert self.get_attr(hierarchy_tl[0], attr_name) == "same"

    @pytest.mark.parametrize("attr_name", ATTRS)
    def test_identical_values_with_empties_kept_without_separator(
        self, hierarchy_tl, attr_name
    ):
        hrcs = self.create_units_to_merge(hierarchy_tl, 4)
        self.set_attr(hrcs[0], attr_name, "same")
        self.set_attr(hrcs[2], attr_name, "same")

        hierarchy_tl.merge(hrcs)

        assert self.get_attr(hierarchy_tl[0], attr_name) == "same"

    def test_identical_colors_kept(self, hierarchy_tl):
        hrcs = self.create_units_to_merge(hierarchy_tl, 3)
        for h in hrcs:
            h.set_data("color", "#aabbcc")

        hierarchy_tl.merge(hrcs)

        assert hierarchy_tl[0].get_data("color") == "#aabbcc"

    def test_differing_colors_not_set(self, hierarchy_tl):
        hrcs = self.create_units_to_merge(hierarchy_tl, 2)
        hrcs[0].set_data("color", "#aabbcc")
        hrcs[1].set_data("color", "#ddeeff")

        hierarchy_tl.merge(hrcs)

        assert hierarchy_tl[0].get_data("color") == ""
