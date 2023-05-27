from tilia import settings
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.cli.timelines.base import TimelineUI


class BeatTimelineUI(TimelineUI):
    TIMELINE_KIND = TimelineKind.BEAT_TIMELINE
    height = 35
    is_visible = True
