"""
Showing a beat timeline's time signatures, which also grows the timeline by
the band they are drawn in. Free of Qt, so the CLI shares it with the Qt UI.
"""

from __future__ import annotations

from typing import Any

from tilia.requests import Get, get
from tilia.settings import settings
from tilia.ui.consts import BEAT_TIMELINE_TIME_SIGNATURE_BAND_HEIGHT


def get_creation_args(height: int | None = None) -> dict[str, Any]:
    """
    Arguments that give a new beat timeline its time signatures and room for
    them. Without `height`, it is the default height plus the band.
    """
    if height is None:
        height = (
            settings.get("beat_timeline", "default_height")
            + BEAT_TIMELINE_TIME_SIGNATURE_BAND_HEIGHT
        )
    return {"show_time_signatures": True, "height": height}


def set_time_signatures_shown(timeline_id: int | str, show: bool) -> bool:
    """
    Shows or hides a beat timeline's time signatures, growing or shrinking it
    by their band. Returns whether anything changed.
    """
    collection = get(Get.TIMELINE_COLLECTION)
    timeline = collection.get_timeline(timeline_id)
    if timeline.show_time_signatures == show:
        return False

    height_change = BEAT_TIMELINE_TIME_SIGNATURE_BAND_HEIGHT
    if not show:
        height_change = -height_change
    collection.set_timeline_data(timeline_id, "show_time_signatures", show)
    collection.set_timeline_data(timeline_id, "height", timeline.height + height_change)
    return True
