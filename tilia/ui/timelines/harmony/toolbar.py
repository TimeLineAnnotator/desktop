from __future__ import annotations

from tilia.ui.actions import TiliaAction
from tilia.ui.timelines.toolbar import TimelineToolbar


class HarmonyTimelineToolbar(TimelineToolbar):
    ACTIONS = [
        TiliaAction.HARMONY_ADD,
        TiliaAction.HARMONY_DELETE,
        TiliaAction.HARMONY_DISPLAY_AS_ROMAN_NUMERAL,
        TiliaAction.HARMONY_DISPLAY_AS_CHORD_SYMBOL,
        TiliaAction.MODE_ADD,
        TiliaAction.MODE_DELETE,
    ]
