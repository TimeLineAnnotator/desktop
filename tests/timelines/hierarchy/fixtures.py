import functools

import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.hierarchy.components import Hierarchy
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.hierarchy import HierarchyTimelineUI, HierarchyUI


class TestHierarchyTimelineUI(HierarchyTimelineUI):
    def create_hierarchy(
        self, start: float, end: float, level: int, **kwargs
    ) -> tuple[Hierarchy | None, HierarchyUI | None]: ...

    def relate_hierarchies(self, parent: Hierarchy, children: list[Hierarchy]): ...


@pytest.fixture
def hierarchy_tlui(hierarchy_tl, tluis) -> TestHierarchyTimelineUI:
    ui = tluis.get_timeline_ui(hierarchy_tl.id)

    ui.create_hierarchy = hierarchy_tl.create_hierarchy
    ui.relate_hierarchies = hierarchy_tl.relate_hierarchies
    ui.create_component = hierarchy_tl.create_component
    return ui  # will be deleted by tls


@pytest.fixture
def hierarchy_tl(tls):
    def relate_hierarchies(parent: Hierarchy, children: list[Hierarchy]):
        # noinspection PyProtectedMember
        return tl.component_manager._update_genealogy(parent, children)

    tl: HierarchyTimeline = tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
    tl.create_initial_hierarchy = lambda self: None

    # remove initial hierarchy
    tl.clear()

    tl.create_hierarchy = functools.partial(tl.create_component, ComponentKind.HIERARCHY)
    tl.relate_hierarchies = relate_hierarchies
    return tl
