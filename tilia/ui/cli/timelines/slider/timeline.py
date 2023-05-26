from tilia import settings
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.cli.timelines.base import TimelineUI


class SliderTimelineUI(TimelineUI):
    TIMELINE_KIND = TimelineKind.SLIDER_TIMELINE
    height = settings.get("slider_timeline", "default_height")
    is_visible = True
