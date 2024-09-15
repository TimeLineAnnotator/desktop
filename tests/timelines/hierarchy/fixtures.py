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
def hierarchy_tlui(tls, tluis) -> TestHierarchyTimelineUI:
    def relate_hierarchies(parent: Hierarchy, children: list[Hierarchy]):
        # noinspection PyProtectedMember
        return tl.component_manager._update_genealogy(parent, children)

    tl: HierarchyTimeline = tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
    tl.create_initial_hierarchy = lambda self: None
    ui = tluis.get_timeline_ui(tl.id)

    # remove initial hierarchy
    tl.clear()

    tl.create_hierarchy = functools.partial(tl.create_component, ComponentKind.HIERARCHY)
    ui.create_hierarchy = tl.create_hierarchy
    tl.relate_hierarchies = relate_hierarchies
    ui.relate_hierarchies = relate_hierarchies
    ui.create_component = tl.create_component
    return ui  # will be deleted by tls


@pytest.fixture
def hierarchy_tl(hierarchy_tlui):
    return hierarchy_tlui.timeline
