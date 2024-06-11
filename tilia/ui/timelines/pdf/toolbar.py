from __future__ import annotations

from tilia.ui.actions import TiliaAction
from tilia.ui.timelines.toolbar import TimelineToolbar


class PdfTimelineToolbar(TimelineToolbar):
    ACTIONS = [TiliaAction.PDF_MARKER_ADD]
