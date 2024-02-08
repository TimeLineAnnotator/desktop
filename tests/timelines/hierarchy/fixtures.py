import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.hierarchy.components import Hierarchy
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.hierarchy import HierarchyTimelineUI, HierarchyUI


class TestHierarchyTimelineUI(HierarchyTimelineUI):
    def create_hierarchy(
        self, start: float, end: float, level: int, **kwargs
    ) -> tuple[Hierarchy, HierarchyUI]: ...

    def relate_hierarchies(self, parent: Hierarchy, children: list[Hierarchy]): ...


@pytest.fixture
def hierarchy_tlui(tilia, tls, tluis) -> TestHierarchyTimelineUI:
    def create_hierarchy(
        start: float, end: float, level: int, **kwargs
    ) -> tuple[Hierarchy | None, HierarchyUI | None]:
        component = tl.create_timeline_component(
            ComponentKind.HIERARCHY, start, end, level, **kwargs
        )
        element = ui.get_element(component.id) if component else None
        return component, element

    def relate_hierarchies(parent: Hierarchy, children: list[Hierarchy]):
        # noinspection PyProtectedMember
        return tl.component_manager._update_genealogy(parent, children)

    tl: HierarchyTimeline = tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
    tl.create_initial_hierarchy = lambda self: None
    ui = tluis.get_timeline_ui(tl.id)

    # remove initial hierarchy
    tl.clear()

    ui.create_hierarchy = create_hierarchy
    ui.relate_hierarchies = relate_hierarchies
    return ui  # will be deleted by tls


@pytest.fixture
def hierarchy_tl(hierarchy_tlui):
    return hierarchy_tlui.timeline
