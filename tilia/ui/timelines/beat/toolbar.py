from __future__ import annotations

from tilia.ui.timelines.toolbar import TimelineToolbar


class BeatTimelineToolbar(TimelineToolbar):
    COMMANDS = [
        "timeline.beat.add",
        "timeline.beat.distribute",
        "timeline.beat.set_measure_number",
        "timeline.beat.reset_measure_number",
        "timeline.beat.toggle_recalculate_measures",
    ]
