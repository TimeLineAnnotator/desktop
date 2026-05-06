from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontMetrics


def elide_text(text: str, font: QFont, max_width: float) -> str:
    """Return `text` truncated with ellipsis to fit within `max_width` pixels.

    Empty input returns "". A non-positive `max_width` returns "" so a
    label whose container has collapsed renders nothing rather than a stray
    ellipsis.
    """
    if not text or max_width <= 0:
        return ""
    return QFontMetrics(font).elidedText(
        text, Qt.TextElideMode.ElideRight, int(max_width)
    )
