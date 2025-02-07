from __future__ import annotations

import functools
import itertools
from typing import Any

from tilia.settings import settings
from tilia.timelines.base.component.segmentlike import (
    scale_segmentlike,
    crop_segmentlike,
)
from ..base.timeline import Timeline, TimelineComponentManager
from tilia.timelines.component_kinds import ComponentKind
from tilia.requests import post, Post, get, Get
from tilia.timelines.timeline_kinds import TimelineKind
from .components import Hierarchy
import tilia.errors
from ...ui.format import format_media_time


class HierarchyTLComponentManager(TimelineComponentManager):
    def __init__(self, timeline: HierarchyTimeline):
        super().__init__(timeline, [ComponentKind.HIERARCHY])
        self.scale = functools.partial(scale_segmentlike, self)
        self.crop = functools.partial(crop_segmentlike, self)

    def _validate_component_creation(
        self, _, start: float, end: float, level: int, **kwargs
    ):
        return Hierarchy.validate_creation(
            start, end, (start, end, level), {(c.start, c.end, c.level) for c in self}
        )

    def deserialize_components(self, components: dict[int, dict[str, Any]]):
        self.clear()  # remove starting hierarchy

        super().deserialize_components(components)

    def get_parent(self, child):
        candidates = {
            h
            for h in self
            if h.start <= child.start and h.end >= child.end and h.level > child.level
        }
        if not candidates:
            return None
        return sorted(candidates, key=lambda h: h.level)[0]

    def get_children(self, parent):
        def get_hierarchies_below(above, hierarchy_iter):
            return {
                h
                for h in hierarchy_iter
                if above.start <= h.start
                and above.end >= h.end
                and above.level > h.level
            }

        remaining_candidates = get_hierarchies_below(parent, self).copy()
        for lvl in reversed([h.level for h in remaining_candidates]):
            for h in {h for h in remaining_candidates if h.level == lvl}:
                remaining_candidates = remaining_candidates.difference(
                    get_hierarchies_below(h, remaining_candidates)
                )

        return sorted(list(remaining_candidates))

    def get_boundary_conflicts(self) -> list[tuple[Hierarchy, Hierarchy]]:
        """
        Returns a list with of tuples with conflicting hierarchies. Returns an empty
        list if there are no conflicts.
        """

        conflicts = []

        for hrc1, hrc2 in itertools.combinations(self._components, 2):
            if hrc1.start < hrc2.start < hrc1.end or hrc1.start < hrc2.end < hrc1.end:
                # hrc2 starts or ends inside hrc1
                if hrc2.level >= hrc1.level:
                    # if it is on the same level or higher, there's a conflict
                    conflicts.append((hrc1, hrc2))
                elif not hrc1.start > hrc2.start and hrc1.end < hrc2.end:
                    # if it doesn't start AND end inside, there's a conflict
                    conflicts.append((hrc1, hrc2))

            # repeat swapping hr1 and hrc2
            if hrc2.start < hrc1.start < hrc2.end or hrc2.start < hrc1.end < hrc2.end:
                if hrc1.level >= hrc2.level:
                    conflicts.append((hrc2, hrc1))
                elif not hrc2.start > hrc1.start and hrc2.end < hrc1.end:
                    conflicts.append((hrc2, hrc1))

            if (
                hrc1.start == hrc2.start
                and hrc1.end == hrc2.end
                and hrc1.level == hrc2.level
            ):
                # if hierachies have same times and level, there's a conflict
                conflicts.append((hrc1, hrc2))

        return conflicts

    def create_child(self, hierarchy: Hierarchy):
        """Create unit one level below with same start and end."""

        def _validate_create_unit_below(h: Hierarchy):
            if h.level == 1:
                return False, "Component is already at lowest level."
            if h.children:
                for child in h.children:
                    if child.level == h.level - 1:
                        return False, "Component would overlap with existing component."
            return True, ""

        success, reason = _validate_create_unit_below(hierarchy)
        if not success:
            return success, reason

        # create new child
        created_unit, fail_reason = self.timeline.create_component(
            kind=ComponentKind.HIERARCHY,
            start=hierarchy.start,
            end=hierarchy.end,
            level=hierarchy.level - 1,
        )

        if not created_unit:
            return False, f"Could not create component below: {reason}"

        return True, ""

    def group(self, hierarchies: list[Hierarchy]):
        def _validate_at_least_two_selected(units_to_group):
            if len(units_to_group) <= 1:
                return False, "At least two components must be selected."
            return True, ""

        def _validate_no_boundary_crossing(start: float, end: float, group_level: int):
            units_to_check = [
                unit for unit in self._components if unit not in hierarchies
            ]

            for unit_to_check in units_to_check:
                start_inside_group = start <= unit_to_check.start < end
                ends_inside_group = start < unit_to_check.end <= end
                comprehends_group = (
                    unit_to_check.start <= start and end <= unit_to_check.end
                )

                if (
                    # if unit_to_check either (1) starts inside and does not
                    # end inside or (2) starts outside and ends inside it is
                    # crossing group boundaries, unless (3) it comprehends
                    # the whole group
                    start_inside_group != ends_inside_group
                    and not comprehends_group
                ) or (
                    # if (1) unit_to_check is at same or higher level and (2) starts
                    # or ends inside the group and (3) does not comprehend group it
                    # is also crossing group boundaries
                    unit_to_check.level >= group_level
                    and (start_inside_group or ends_inside_group)
                    and not comprehends_group
                ):
                    return (
                        False,
                        "Grouping component would overlap with existing component.",
                    )
            return True, ""

        def _validate_no_overlap_in_grouping_level(
            start: float, end: float, grouping_level: int
        ):
            """Raises False if there is a unit in grouping level that spans
            or exceeds the interval between 'start_time' and 'end_time'."""
            if any(
                [
                    u.start <= start < u.end or u.start < end <= u.end
                    for u in [u for u in self.timeline if u.level == grouping_level]
                ]
            ):
                return (
                    False,
                    "Grouping component would overlap with component in same level.",
                )
            return True, ""

        def _get_previous_common_parent(
            units_to_group: list[Hierarchy],
        ) -> Hierarchy | None:
            units_with_parents_outside = [
                unit for unit in units_to_group if unit.parent not in units_to_group
            ]
            parents = {unit.parent for unit in units_with_parents_outside}
            if len(parents) == 1:
                return next(iter(parents))
            else:
                return None

        def is_between_grouped_units(u):
            def has_same_parent():
                return u.parent == _get_previous_common_parent(hierarchies)

            def is_inside_grouping():
                return u.start > earliest_unit.start and u.end < latest_unit.end

            def has_same_level_or_lower():
                return u.level <= max_group_level

            return (
                is_inside_grouping() and has_same_level_or_lower() and has_same_parent()
            )

        success, reason = _validate_at_least_two_selected(hierarchies)
        if not success:
            return success, reason

        earliest_unit = sorted(hierarchies, key=lambda u: u.start)[0]
        latest_unit = sorted(hierarchies, key=lambda u: u.end)[-1]
        start_time = earliest_unit.start
        end_time = latest_unit.end
        max_group_level = max([unit.level for unit in hierarchies])

        success, reason = _validate_no_boundary_crossing(
            start_time, end_time, max_group_level
        )
        if not success:
            return success, reason

        hierarchies += self.get_components_by_condition(
            is_between_grouped_units, kind=ComponentKind.HIERARCHY
        )

        grouping_unit_level = max([unit.level for unit in hierarchies]) + 1

        success, reason = _validate_no_overlap_in_grouping_level(
            start_time, end_time, grouping_unit_level
        )
        if not success:
            return success, reason

        grouping_unit, fail_reason = self.timeline.create_component(
            kind=ComponentKind.HIERARCHY,
            start=start_time,
            end=end_time,
            level=grouping_unit_level,
        )

        if not grouping_unit:
            return False, fail_reason

        return True, ""

    def get_unit_to_split(self, time: float) -> Hierarchy | None:
        """
        Returns lowest level unit that begins
        strictly before and ends strictly after 'time'
        """
        units_at_time = self.get_components_by_condition(
            lambda u: u.start < time < u.end, kind=ComponentKind.HIERARCHY
        )
        units_at_time_sorted_by_time = sorted(units_at_time, key=lambda u: u.level)
        if units_at_time_sorted_by_time:
            return units_at_time_sorted_by_time[0]
        else:
            return None

    def split(self, unit_to_split: Hierarchy, split_time: float):
        """Split a unit into two new ones"""

        def _validate_split(hierarchy: Hierarchy, time: float):
            if not hierarchy.start < time < hierarchy.end:
                return (
                    False,
                    f"Time '{format_media_time(time)}' is outside component.",
                )
            return True, ""

        def pass_on_attributes():
            both_inherit = ["label", "color", "comments"]
            left_inherits = ["pre_start"]
            right_inherits = ["post_end"]

            for attr in both_inherit:
                self.timeline.set_component_data(
                    left_unit.id, attr, getattr(unit_to_split, attr)
                )
                self.timeline.set_component_data(
                    right_unit.id, attr, getattr(unit_to_split, attr)
                )

            for attr in left_inherits:
                self.timeline.set_component_data(
                    left_unit.id, attr, getattr(unit_to_split, attr)
                )

            for attr in right_inherits:
                self.timeline.set_component_data(
                    right_unit.id, attr, getattr(unit_to_split, attr)
                )

        success, reason = _validate_split(unit_to_split, split_time)
        if not success:
            return success, reason

        post(Post.LOOP_IGNORE_COMPONENT, self.timeline.id, unit_to_split.id)
        self.delete_component(unit_to_split)

        left_unit, fail_reason = self.timeline.create_component(
            kind=ComponentKind.HIERARCHY,
            start=unit_to_split.start,
            end=split_time,
            level=unit_to_split.level,
        )

        if not left_unit:
            return False, fail_reason

        right_unit, fail_reason = self.timeline.create_component(
            kind=ComponentKind.HIERARCHY,
            start=split_time,
            end=unit_to_split.end,
            level=unit_to_split.level,
        )

        if not right_unit:
            return False, fail_reason

        pass_on_attributes()

        post(
            Post.HIERARCHY_MERGE_SPLIT_DONE,
            [
                (left_unit.timeline.id, left_unit.id),
                (right_unit.timeline.id, right_unit.id),
            ],
            [(unit_to_split.timeline.id, unit_to_split.id)],
        )

        return True, ""

    def merge(self, hierarchies: list[Hierarchy]):
        def _validate_at_least_two_units(units: list[Hierarchy]):
            if len(units) <= 1:
                return False, "At least two components are needed."
            return True, ""

        def _validate_at_same_level(hs: list[Hierarchy]):
            if any(h.level != hs[0].level for h in hs):
                return False, "Components need to be at the same level."
            return True, ""

        def _validate_common_parent(hs: list[Hierarchy]):
            if any(h.parent != hs[0].parent for h in hs):
                return False, "Components need to have a common parent."
            return True, ""

        def _get_units_to_merge_from_unit_list(
            hs: list[Hierarchy],
        ) -> list[Hierarchy]:
            """
            Returns units that:
            (1) start after (inclusive) first given unit's start;
            (2) end before (inclusive) last given unit's end; and
            (3) have the same parent as given units.
            Assumes all given units have the same parent.
            """

            def sort_by_time(h):
                return h.start, h.end

            # get units between extremities
            def is_between_selected_units_and_has_same_parent(h: Hierarchy):
                units_sorted_by_time = sorted(hs, key=sort_by_time)
                return (
                    h.start >= units_sorted_by_time[0].end
                    and h.end <= units_sorted_by_time[-1].start
                    and h.parent == hs[0].parent
                )

            units_between = self.get_components_by_condition(
                is_between_selected_units_and_has_same_parent,
                kind=ComponentKind.HIERARCHY,
            )

            return list(set(hs + units_between))

        success, reason = _validate_common_parent(hierarchies)
        if not success:
            return success, reason

        success, reason = _validate_at_least_two_units(hierarchies)
        if not success:
            return success, reason
        hierarchies = sorted(
            _get_units_to_merge_from_unit_list(hierarchies), key=lambda u: u.start
        )
        success, reason = _validate_at_same_level(hierarchies)
        if not success:
            return success, reason

        for unit in hierarchies:
            post(Post.LOOP_IGNORE_COMPONENT, self.timeline.id, unit.id)
            self.delete_component(unit)

        merger_unit, fail_reason = self.timeline.create_component(
            kind=ComponentKind.HIERARCHY,
            start=hierarchies[0].start,
            end=hierarchies[-1].end,
            level=hierarchies[0].level,
        )

        if not merger_unit:
            return False, fail_reason

        post(
            Post.HIERARCHY_MERGE_SPLIT_DONE,
            [(merger_unit.timeline.id, merger_unit.id)],
            [(hierarchy.timeline.id, hierarchy.id) for hierarchy in hierarchies],
        )

        return True, ""

    def delete_component(self, component: Hierarchy, **kwargs) -> None:
        super().delete_component(component, **kwargs)


class HierarchyTimeline(Timeline):
    KIND = TimelineKind.HIERARCHY_TIMELINE
    COMPONENT_MANAGER_CLASS = HierarchyTLComponentManager

    @property
    def default_height(self):
        return settings.get("hierarchy_timeline", "default_height")

    def setup_blank_timeline(self):
        """Create unit of level 1 encompassing whole timeline"""
        self.create_component(
            kind=ComponentKind.HIERARCHY,
            start=0,
            end=get(Get.MEDIA_DURATION),
            level=1,
        )

    def _validate_delete_components(self, component: Hierarchy) -> None:
        pass

    def create_children(self, components: list[Hierarchy]) -> bool:
        results = []
        for component in components:
            success, reason = self.component_manager.create_child(component)
            if not success:
                tilia.errors.display(tilia.errors.HIERARCHY_CREATE_CHILD_FAILED, reason)

            results.append(success)

        return any(results)

    def alter_levels(self, components: list[Hierarchy], amount: int) -> bool:
        def validate_level(hierarchy, level):
            if level < 1:
                return False, "minimum level is 1."
            elif hierarchy.parent and hierarchy.parent.level == level:
                return False, "would overlap with parent."

            max_child_level = 0
            for child in hierarchy.children:
                max_child_level = max(max_child_level, child.level)
            if level <= max_child_level:
                return False, "would overlap with children."
            return True, ""

        if not amount:
            return False

        result = []
        for component in components:
            success, reason = validate_level(component, component.level + amount)
            if not success:
                tilia.errors.display(tilia.errors.HIERARCHY_CHANGE_LEVEL_FAILED, reason)
                continue

            self.component_manager.set_component_data(
                component.id, "level", component.level + amount
            )

            result.append(success)

        return any(result)

    def group(self, components: list[Hierarchy]) -> None:
        success, reason = self.component_manager.group(components)
        if not success:
            tilia.errors.display(tilia.errors.HIERARCHY_GROUP_FAILED, reason)
        return success

    def split(self, time: float) -> bool:
        unit_to_split = self.component_manager.get_unit_to_split(time)
        if not unit_to_split:
            return False

        success, reason = self.component_manager.split(unit_to_split, time)
        if not success:
            tilia.errors.display(tilia.errors.HIERARCHY_SPLIT_FAILED, reason)

        return success

    def merge(self, units: list[Hierarchy]) -> None:
        success, reason = self.component_manager.merge(units)
        if not success:
            tilia.errors.display(tilia.errors.HIERARCHY_MERGE_FAILED, reason)
        return success

    def get_boundary_conflicts(self):
        return self.component_manager.get_boundary_conflicts()
