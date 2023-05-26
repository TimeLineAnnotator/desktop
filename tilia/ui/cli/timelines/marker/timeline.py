from tilia import settings
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.cli.timelines.base import TimelineUI


class MarkerTimelineUI(TimelineUI):
    TIMELINE_KIND = TimelineKind.MARKER_TIMELINE
    height = settings.get("marker_timeline", "default_height")
    is_visible = True
