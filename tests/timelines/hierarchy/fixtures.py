import pytest

from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.hierarchy.components import Hierarchy
from tilia.timelines.hierarchy.timeline import HierarchyTimeline
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.hierarchy import HierarchyTimelineUI, HierarchyUI


class TestHierarchyTimelineUI(HierarchyTimelineUI):
    def create_component(self, _: ComponentKind, *args, ** kwargs): ...

    def create_hierarchy(
        self, start: float, end: float, level: int, **kwargs
    ) -> tuple[Hierarchy | None, HierarchyUI | None]: ...

    def relate_hierarchies(self, parent: Hierarchy, children: list[Hierarchy]): ...


@pytest.fixture
def hierarchy_tlui(tls, tluis) -> TestHierarchyTimelineUI:
    def create_component(_: ComponentKind, *args, **kwargs):
        return create_hierarchy(*args, **kwargs)

    def create_hierarchy(
        start: float = 0, end: float = None, level: int = 1, **kwargs
    ) -> tuple[Hierarchy | None, HierarchyUI | None]:
        if end is None:
            end = start + 1
        component, _ = tl.create_timeline_component(
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

    tl.create_hierarchy = create_hierarchy
    ui.create_hierarchy = create_hierarchy
    tl.relate_hierarchies = relate_hierarchies
    ui.relate_hierarchies = relate_hierarchies
    tl.create_component = create_component
    ui.create_component = create_component
    return ui  # will be deleted by tls


@pytest.fixture
def hierarchy_tl(hierarchy_tlui):
    return hierarchy_tlui.timeline
