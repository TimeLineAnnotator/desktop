from __future__ import annotations

from tilia.ui.timelines.toolbar import TimelineToolbar


class HarmonyTimelineToolbar(TimelineToolbar):
    ACTIONS = [
        "harmony_add",
        "mode_add",
        "harmony_display_as_roman_numeral",
        "harmony_display_as_chord_symbol",
    ]
