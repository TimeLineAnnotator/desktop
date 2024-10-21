from __future__ import annotations

from tilia.ui.actions import TiliaAction
from tilia.ui.timelines.toolbar import TimelineToolbar


class BeatTimelineToolbar(TimelineToolbar):
    ACTIONS = [
        TiliaAction.BEAT_ADD,
        TiliaAction.BEAT_DISTRIBUTE,
        TiliaAction.BEAT_SET_MEASURE_NUMBER,
        TiliaAction.BEAT_RESET_MEASURE_NUMBER,
    ]
