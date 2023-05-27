from __future__ import annotations
from typing import TYPE_CHECKING

from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.ui.cli.timelines.base import TimelineUI

if TYPE_CHECKING:
    from tilia.ui.cli.ui import CLI


class TimelineUICollection:
    def __init__(self, app_ui: CLI):
        self.app_ui = app_ui
        self._timeline_uis = []

    @property
    def timeline_uis(self):
        return self._timeline_uis

    def create_timeline_ui(self, kind: TlKind, name: str, **kwargs) -> TimelineUI:
        timeline_class = self.get_timelineui_class(kind)

        tl_ui = timeline_class(name, display_position=len(self._timeline_uis), **kwargs)
        self._timeline_uis.append(tl_ui)
        return tl_ui

    def delete_timeline_ui(self, tlui: TimelineUI):
        try:
            self._timeline_uis.remove(tlui)
        except ValueError:
            # TimelineUI not in collection. Maybe it was already deleted?
            # TODO: output a warning to the user
            pass

        pass

    def get_timelineui_class(self, kind: TlKind):
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

        return kind_to_class_dict[kind]
