from __future__ import annotations
from typing import TYPE_CHECKING

from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.protocol.timelines.timeline import TimelineUI

if TYPE_CHECKING:
    from tilia.ui.protocol.ui import UI


class TimelineUICollection:
    app_ui: UI

    def create_timeline_ui(self, kind: TimelineKind, name: str, **kwargs) -> TimelineUI:
        ...
