from __future__ import annotations

from tilia.ui.timelines.toolbar import TimelineToolbar


class MarkerTimelineToolbar(TimelineToolbar):
    ACTIONS = ["marker_add"]
    # from tilia.ui.qactions import get_qaction
    # ACTIONS = [get_qaction("timelines.marker.add_component")]
