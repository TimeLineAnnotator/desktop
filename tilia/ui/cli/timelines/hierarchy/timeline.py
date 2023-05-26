from tilia import settings
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.cli.timelines.base import TimelineUI


class HierarchyTimelineUI(TimelineUI):
    TIMELINE_KIND = TimelineKind.HIERARCHY_TIMELINE
    height = settings.get("hierarchy_timeline", "default_height")
    is_visible = True
