from __future__ import annotations

import math

from tilia.ui.format import format_media_time


def shown_time(time: float) -> str:
    """A time as the texts of TiLiA's own checks show it: a media time. One that
    isn't a finite number, or is too large for a float, is shown as it is ("inf"),
    as the core's texts show it: `format_media_time` can't take it."""
    try:
        finite = math.isfinite(time)
    except OverflowError:  # an integer too large for a float
        finite = False
    return format_media_time(time) if finite else f"{time}"
