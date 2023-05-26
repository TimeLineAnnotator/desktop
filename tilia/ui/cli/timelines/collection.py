from __future__ import annotations
from typing import TYPE_CHECKING

from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.cli.timelines.timeline import TimelineUI

if TYPE_CHECKING:
    from tilia.ui.cli.ui import CLI


class TimelineUICollection:
    def __init__(self, app_ui: CLI):
        self.app_ui = app_ui

    def create_timeline_ui(self, kind: TimelineKind, name: str, **kwargs) -> TimelineUI:
        return TimelineUI()
