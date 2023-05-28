from __future__ import annotations

import logging
import itertools

from tilia import events, settings
from .common import update_component_genealogy
from ..base.timeline import Timeline, TimelineComponentManager
from tilia.timelines.component_kinds import ComponentKind
from tilia.events import Event, post
from tilia.timelines.timeline_kinds import TimelineKind
from .components import Hierarchy, HierarchyOperationError
from tilia.timelines.common import (
    log_object_creation,
)
from ...exceptions import CreateComponentError

logger = logging.getLogger(__name__)


class HierarchyTimeline(Timeline):
    KIND = TimelineKind.HIERARCHY_TIMELINE
    DEFAULT_HEIGHT = settings.get("hierarchy_timeline", "default_height")

    @property
    def ordered_hierarchies(self):
        return self.component_manager.ordered_hierarchies

    def create_hierarchy(
        self, start: float, end: float, level: int, **kwargs
    ) -> Hierarchy:
        return self.create_timeline_component(
            ComponentKind.HIERARCHY, start, end, level, **kwargs
        )

    def create_initial_hierarchy(self):
        """Create unit of level 1 encompassing whole timeline"""
        logging.debug(f"Creating starting hierarchy for timeline '{self}'")
        self.create_timeline_component(
            kind=ComponentKind.HIERARCHY,
            start=0,
            end=self.get_media_length(),
            level=1,
        )

        events.post(Event.HIERARCHY_TIMELINE_UI_CREATED_INITIAL_HIERARCHY, self.id)

    def _validate_delete_components(self, component: Hierarchy) -> None:
        pass

    def create_unit_below(self, component: Hierarchy) -> None:
        self.component_manager.create_unit_below(component)

    def change_level(self, amount: int, components: list[Hierarchy]) -> None:
        if amount > 0:
            reverse = True
        elif amount < 0:
            reverse = False
        else:
            return

        for component in sorted(
            components, key=lambda x: (x.level, x.start), reverse=reverse
        ):
            self.component_manager.change_level(component, amount)

    def group(self, units: list[Hierarchy]) -> None:
        self.component_manager.group(units)

    def split(self, time: float) -> None:
        unit_to_split = self.component_manager.get_unit_to_split(time)
        if not unit_to_split:
            logger.debug(f"No hierarchy at the current playback level. Can not split.")
            return
        self.component_manager.split(unit_to_split, time)

    def merge(self, units: list[Hierarchy]) -> None:
        self.component_manager.merge(units)

    def scale(self, factor: float) -> None:
        self.component_manager.scale(factor)

    def crop(self, length: float) -> None:
        self.component_manager.crop(length)

    def do_genealogy(self):
        self.component_manager.do_genealogy()

    def get_boundary_conflicts(self):
        return self.component_manager.get_boundary_conflicts()


class HierarchyTLComponentManager(TimelineComponentManager):
    COMPONENT_TYPES = [ComponentKind.HIERARCHY]

    @log_object_creation
    def __init__(self):
        super().__init__(self.COMPONENT_TYPES)

    def _validate_component_creation(
        self,
        timeline: HierarchyTimeline,
        start: float,
        end: float,
        level: int,
        parent=None,
        children=None,
        comments="",
        pre_start=None,
        post_end=None,
        formal_type="",
        formal_function="",
        **_,
    ):
        media_length = self.timeline.get_media_length()
        if start > media_length:
            raise CreateComponentError(
                f"Start time '{start}' is bigger than medium time '{media_length}'"
            )

        if end > media_length:
            raise CreateComponentError(
                f"End time '{end}' is bigger than medium time '{media_length}'"
            )

        if end <= start:
            raise CreateComponentError(
                f"End time '{end}' should be bigger than start time '{start}'"
            )

    def deserialize_components(self, serialized_components: dict[int, dict[str]]):
        self.clear()  # TODO temporary solution to remove starting hierarchy

        super().deserialize_components(serialized_components)

        post(Event.HIERARCHY_COMPONENTS_DESERIALIZED, self.timeline.id)

    def _update_genealogy(self, parent: Hierarchy, children: list[Hierarchy]):
        """
        Calls genealogy update on timeline and timeline UI
        """

        update_component_genealogy(parent, children)
        self.post_component_event(
            Event.HIERARCHY_GENEALOGY_CHANGED, parent.id, [c.id for c in children]
        )

    def do_genealogy(self):
        """
        Sets parent and children attributes of all timelines based on their
        position and level. Previous parent/child relations are ignored.
        Assumes child and parent attributes are empty for all hierarchies involved.
        Very inefficient, but should be good enough for now.
        """
        ordered_hierarchies = self.ordered_hierarchies

        for lvl in sorted([hrc.level for hrc in self._components]):
            for child in [hrc for hrc in self._components if hrc.level == lvl]:
                for hrc in ordered_hierarchies:
                    if (
                        not child.parent
                        and child.start >= hrc.start
                        and child.end <= hrc.end
                        and child.level < hrc.level
                    ):
                        child.parent = hrc
                        hrc.children += [child]
                        break

    @property
    def ordered_hierarchies(self):
        return sorted([h for h in self._components], key=lambda x: (x.level, x.start))

    def get_boundary_conflicts(self) -> list[tuple[Hierarchy, Hierarchy]]:
        """
        Returns a list with of tuples with conflicting hierarchies. Returns an empty list
        if there are no conflicts.
        """

        conflicts = []

        for hrc1, hrc2 in itertools.combinations(self._components, 2):
            if hrc1.start < hrc2.start < hrc1.end or hrc1.start < hrc2.end < hrc1.end:
                # hrc2 starts or ends inside hrc1
                if hrc2.level >= hrc1.level:
                    # if its on the same level or higher, there's a conflict
                    conflicts.append((hrc1, hrc2))
                elif not hrc1.start > hrc2.start and hrc1.end < hrc2.end:
                    # if its doesn't start AND end inside, there's a conflict
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

    def create_unit_below(self, unit: Hierarchy):
        """Create child unit one level below with same start and end.
        Returns parent/child relation between unit and unit created below.
        """

        def _validate_create_unit_below(unit: Hierarchy) -> None:
            if unit.level == 1:
                raise HierarchyOperationError(
                    f"Can't create unit below: unit {unit} is at lowest level."
                )
            if unit.children:
                for child in unit.children:
                    if child.level == unit.level - 1:
                        raise HierarchyOperationError(
                            f"Can't create unit below: child '{child}' already exists at intended level."
                        )

        _validate_create_unit_below(unit)

        # create new child
        created_unit = self.timeline.create_timeline_component(
            kind=ComponentKind.HIERARCHY,
            start=unit.start,
            end=unit.end,
            level=unit.level - 1,
        )

        if unit.children:
            logging.debug(f"Making former children child to unit created below {self}.")
            self._update_genealogy(created_unit, unit.children)
        else:
            logging.debug(
                f"No previous children. No need to make them child of unit created below."
            )

        # make parent/child relation between unit and create unit
        self._update_genealogy(unit, [created_unit])

    def change_level(self, unit: Hierarchy, amount: int):
        def _validate_change_level(unit: Hierarchy, new_level: int):
            if new_level < 1:
                raise HierarchyOperationError(
                    f"Can't change level: new level would be < 1."
                )
            elif unit.parent and unit.parent.level <= new_level:
                raise HierarchyOperationError(
                    f"Can't change level: new level would be >= parent level."
                )

            max_child_level = 0
            for child in unit.children:
                max_child_level = max(max_child_level, child.level)
            if new_level <= max_child_level:
                raise HierarchyOperationError(
                    f"Can't change level: new level would be <= child level."
                )

        prev_level = unit.level
        new_level = unit.level + amount

        _validate_change_level(unit, new_level)
        unit.level = new_level

        self.post_component_event(
            Event.HIERARCHY_LEVEL_CHANGED, unit.id, prev_level, new_level
        )
        self.post_component_event(Event.HIERARCHY_POSITION_CHANGED, unit.id)

    def group(self, units_to_group: list[Hierarchy]) -> None:
        def _validate_at_least_two_selected(units_to_group):
            if len(units_to_group) <= 1:
                raise HierarchyOperationError(
                    f"Can't group: at least two units are needed to group"
                )

        def _validate_no_boundary_crossing(start_time: float, end_time: float):
            units_to_check = [
                unit for unit in self._components if unit not in units_to_group
            ]

            for unit_to_check in units_to_check:
                start_inside_grouping = start_time <= unit_to_check.start < end_time
                ends_inside_grouping = start_time < unit_to_check.end <= end_time
                comprehends_grouping = (
                    unit_to_check.start <= start_time and end_time <= unit_to_check.end
                )

                # if unit_to_check either (1) starts inside and does not
                # end inside or (2) starts outside and ends inside it is
                # crossing grouping boundaries, unless (3) it comprehends
                # the whole grouping
                if (
                    start_inside_grouping != ends_inside_grouping
                    and not comprehends_grouping
                ):
                    raise HierarchyOperationError(
                        f"Can't group: grouping unit would cross boundary of {unit_to_check}"
                    )

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

        def _validate_no_overlap_with_higher_unit(
            start_time: float, end_time: float, grouping_unit_level: int
        ):
            """Raises error if there is a unit in grouping level that spans
            or exceeds the interval between 'start_time' and 'end_time'."""
            units_in_grouping_level = [
                unit for unit in self._components if unit.level == grouping_unit_level
            ]
            if bool(
                [
                    u
                    for u in units_in_grouping_level
                    if u.start <= start_time and u.end >= end_time
                ]
            ):
                raise HierarchyOperationError(
                    f"Can't group: grouping unit would overlap with unit in higher level."
                )

        # GROUPING PROPER
        _validate_at_least_two_selected(units_to_group)

        earliest_unit = sorted(units_to_group, key=lambda u: u.start)[0]
        latest_unit = sorted(units_to_group, key=lambda u: u.end)[-1]
        start_time = earliest_unit.start
        end_time = latest_unit.end

        _validate_no_boundary_crossing(start_time, end_time)

        has_same_parent = lambda u: u.parent == _get_previous_common_parent(
            units_to_group
        )
        is_inside_grouping = (
            lambda u: u.start > earliest_unit.start and u.end < latest_unit.end
        )
        is_between_grouped_units = lambda u: has_same_parent(u) and is_inside_grouping(
            u
        )

        units_to_group += self.get_components_by_condition(
            is_between_grouped_units, kind=ComponentKind.HIERARCHY
        )

        # units_to_group = self.get_units_between(earliest_unit, latest_unit, include_extremities=True)

        grouping_unit_level = max([unit.level for unit in units_to_group]) + 1

        _validate_no_overlap_with_higher_unit(start_time, end_time, grouping_unit_level)

        grouping_unit = self.timeline.create_timeline_component(
            kind=ComponentKind.HIERARCHY,
            start=start_time,
            end=end_time,
            level=grouping_unit_level,
        )

        # find out who is supposed to be a children of grouping unit
        previous_common_parent = _get_previous_common_parent(units_to_group)
        grouping_unit_children = [
            unit
            for unit in units_to_group
            if not unit.parent or unit.parent == previous_common_parent
        ]

        # make parent/child relations between grouping unit, children units and previous cmmon parent (if existing)
        self._update_genealogy(grouping_unit, grouping_unit_children)

        if previous_common_parent:
            previous_parent_new_children = [
                c for c in previous_common_parent.children if c not in units_to_group
            ] + [grouping_unit]

            self._update_genealogy(previous_common_parent, previous_parent_new_children)

        # TODO handle selects and deselects

    def get_unit_to_split(self, time: float) -> Hierarchy | None:
        """Returns lowest level unit that begins strictly before and ends strictly after 'time'"""
        units_at_time = self.get_components_by_condition(
            lambda u: u.start < time < u.end, kind=ComponentKind.HIERARCHY
        )
        units_at_time_sorted_by_time = sorted(units_at_time, key=lambda u: u.level)
        if units_at_time_sorted_by_time:
            return units_at_time_sorted_by_time[0]

    def split(self, unit_to_split: Hierarchy, split_time: float) -> None:
        """Split a unit into two new ones"""

        def _validate_split(unit: Hierarchy, time: float):
            if not unit.start < time < unit.end:
                raise HierarchyOperationError(
                    f"Can't split: time '{time}' is not inside unit '{unit}' boundaries."
                )

        def _get_new_children_for_unit_to_split_parent(
            unit_to_split, left_unit, right_unit
        ):
            new_children = unit_to_split.parent.children.copy() + [
                left_unit,
                right_unit,
            ]

            return new_children

        _validate_split(unit_to_split, split_time)

        self.delete_component(unit_to_split)

        left_unit = self.timeline.create_timeline_component(
            kind=ComponentKind.HIERARCHY,
            start=unit_to_split.start,
            end=split_time,
            level=unit_to_split.level,
        )

        right_unit = self.timeline.create_timeline_component(
            kind=ComponentKind.HIERARCHY,
            start=split_time,
            end=unit_to_split.end,
            level=unit_to_split.level,
        )

        # pass previous parent to new units
        if unit_to_split.parent:
            self._update_genealogy(
                unit_to_split.parent,
                _get_new_children_for_unit_to_split_parent(
                    unit_to_split, left_unit, right_unit
                ),
            )

        # pass previous children to new units
        if unit_to_split.children:
            self._update_genealogy(
                left_unit,
                [child for child in unit_to_split.children if child.start < split_time],
            )

            self._update_genealogy(
                right_unit,
                [
                    child
                    for child in unit_to_split.children
                    if child.start >= split_time
                ],
            )

        UI_ATTRIBUTES_TO_PASS_ON = ["label", "color"]

        TL_COMPONENT_ATTRIBUTES_TO_PASS_ON = ["comments"]

        for attr in TL_COMPONENT_ATTRIBUTES_TO_PASS_ON:
            setattr(left_unit, attr, getattr(unit_to_split, attr))
            setattr(right_unit, attr, getattr(unit_to_split, attr))

    def merge(self, units_to_merge: list[Hierarchy]):
        def _validate_at_least_two_units(units: list[Hierarchy]) -> None:
            if len(units) <= 1:
                raise HierarchyOperationError("Can't merge: need at least two units.")

        def _validate_at_same_level(units: list[Hierarchy]) -> None:
            if any(unit.level != units[0].level for unit in units):
                raise HierarchyOperationError(
                    "Can't merge: units need to be of the same level."
                )

        def _validate_common_parent(units: list[Hierarchy]) -> None:
            if any(unit.parent != units[0].parent for unit in units):
                raise HierarchyOperationError(
                    "Can't merge: units need to have a common parent."
                )

        def _get_units_to_merge_from_unit_list(
            units: list[Hierarchy],
        ) -> list[Hierarchy]:
            """
            Returns units that:
            (1) start after (inclusive) first given unit's start;
            (2) end before (inclusive) last given unit's end; and
            (3) have the same parent as given units.
            Assumes all given units have the same parent.
            """

            units_sorted_by_time = sorted(units, key=lambda u: (u.start, u.end))

            # get units between extremities
            is_between_selected_units_and_has_same_parent = lambda u: all(
                [
                    u.start >= units_sorted_by_time[0].end,
                    u.end <= units_sorted_by_time[-1].start,
                    u.parent == units[0].parent,
                ]
            )

            units_between = self.get_components_by_condition(
                is_between_selected_units_and_has_same_parent,
                kind=ComponentKind.HIERARCHY,
            )

            return list(set(units + units_between))

        _validate_common_parent(units_to_merge)
        _validate_at_least_two_units(units_to_merge)
        units_to_merge = sorted(
            _get_units_to_merge_from_unit_list(units_to_merge), key=lambda u: u.start
        )
        _validate_at_same_level(units_to_merge)

        for unit in units_to_merge:
            self.delete_component(unit)

        merger_unit = self.timeline.create_timeline_component(
            kind=ComponentKind.HIERARCHY,
            start=units_to_merge[0].start,
            end=units_to_merge[-1].end,
            level=units_to_merge[0].level,
        )

        previous_parent = units_to_merge[0].parent

        if previous_parent:
            self._update_genealogy(
                previous_parent, previous_parent.children + [merger_unit]
            )

        # get merged_unit children
        merger_children = []
        for unit in units_to_merge:
            merger_children += unit.children

        self._update_genealogy(merger_unit, merger_children)

    def delete_component(self, component: Hierarchy) -> None:
        super().delete_component(component)

        self._update_genealogy_after_deletion(component)

    def scale(self, factor: float) -> None:
        logger.debug(f"Scaling hierarchies in {self}...")
        for hrc in self._components:
            hrc.start *= factor
            hrc.end *= factor
            self.post_component_event(Event.HIERARCHY_POSITION_CHANGED, hrc.id)

    def crop(self, length: float) -> None:
        logger.debug(f"Cropping hierarchies in {self}...")
        for hrc in self._components.copy():
            if hrc.end > length:
                if hrc.start >= length:
                    self.delete_component(hrc)
                else:
                    hrc.end = length
                    self.post_component_event(Event.HIERARCHY_POSITION_CHANGED, hrc.id)

    def _update_genealogy_after_deletion(self, component: Hierarchy) -> None:
        logger.debug(f"Updating component's parent/children relation after deletion...")

        if not component.parent:
            logger.debug(f"Component had no parent.")
            for child in component.children:
                logger.debug(f"Setting previous child={child}'s parent as None")
                child.parent = None
            return

        component_parent_new_children = [
            h for h in component.parent.children if h != component
        ]

        if component.children:
            component_parent_new_children += component.children

        logger.debug(f"Parent's new children are {component_parent_new_children}")

        self._update_genealogy(component.parent, component_parent_new_children)
