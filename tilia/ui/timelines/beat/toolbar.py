from __future__ import annotations

from tilia.ui.timelines.toolbar import TimelineToolbar


class BeatTimelineToolbar(TimelineToolbar):
    ACTIONS = [
        "beat_add",
        "beat_distribute",
        "beat_set_measure_number",
        "beat_reset_measure_number",
    ]
