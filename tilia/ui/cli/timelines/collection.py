from __future__ import annotations
from typing import TYPE_CHECKING

from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.cli.timelines.timeline import TimelineUI

if TYPE_CHECKING:
    from tilia.ui.cli.ui import CLI


class TimelineUICollection:
    def __init__(self, app_ui: CLI):
        self.app_ui = app_ui

    def create_timeline_ui(self, kind: TimelineKind, name: str, **kwargs) -> TimelineUI:
        timeline_class = self.get_timelineui_class(kind)

        tl_ui = timeline_class(name, **kwargs)
        return tl_ui

    def get_timelineui_class(self, kind: TimelineKind):
        from tilia.ui.cli.timelines.hierarchy import HierarchyTimelineUI
        from tilia.ui.cli.timelines.slider import SliderTimelineUI
        from tilia.ui.cli.timelines.marker import MarkerTimelineUI
        from tilia.ui.cli.timelines.beat import BeatTimelineUI

        kind_to_class_dict = {
            TlKind.HIERARCHY_TIMELINE: HierarchyTimelineUI,
            TlKind.SLIDER_TIMELINE: SliderTimelineUI,
            TlKind.MARKER_TIMELINE: MarkerTimelineUI,
            TlKind.BEAT_TIMELINE: BeatTimelineUI,
        }

        class_ = kind_to_class_dict[kind]

        return class_
