from tilia import settings
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.cli.timelines.base import TimelineUI
from tilia.ui.cli.timelines.hierarchy import HierarchyUI


class HierarchyTimelineUI(TimelineUI):
    TIMELINE_KIND = TimelineKind.HIERARCHY_TIMELINE
    ELEMENT_CLASS = HierarchyUI
    height = settings.get("hierarchy_timeline", "default_height")
    is_visible = True
