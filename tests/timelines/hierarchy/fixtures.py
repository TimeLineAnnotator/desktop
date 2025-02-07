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
    ) -> tuple[Hierarchy | None, HierarchyUI | None]:
        ...


@pytest.fixture
def hierarchy_tlui(hierarchy_tl, tluis) -> TestHierarchyTimelineUI:
    ui = tluis.get_timeline_ui(hierarchy_tl.id)

    ui.create_hierarchy = hierarchy_tl.create_hierarchy
    ui.create_component = hierarchy_tl.create_component
    return ui  # will be deleted by tls


@pytest.fixture
def hierarchy_tl(tls):
    tl: HierarchyTimeline = tls.create_timeline(TimelineKind.HIERARCHY_TIMELINE)
    tl.create_initial_hierarchy = lambda self: None

    # remove initial hierarchy
    tl.clear()

    tl.create_hierarchy = functools.partial(
        tl.create_component, ComponentKind.HIERARCHY
    )
    return tl


@pytest.fixture
def hierarchy(hierarchy_tl):
    return hierarchy_tl.create_hierarchy(0, 1, 1)[0]


@pytest.fixture
def hierarchy_ui(hierarchy_tlui, hierarchy):
    return hierarchy_tlui.get_element(hierarchy.id)
