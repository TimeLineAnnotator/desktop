from __future__ import annotations

from tilia.ui.actions import TiliaAction
from tilia.ui.timelines.toolbar import TimelineToolbar


class MarkerTimelineToolbar(TimelineToolbar):
    ACTIONS = [TiliaAction.MARKER_ADD, TiliaAction.MARKER_DELETE]
