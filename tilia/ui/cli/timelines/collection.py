from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tilia.ui.cli.ui import CLI


class TimelineUICollection:
    def __init__(self, app_ui: CLI):
        self.app_ui = app_ui
        self._timeline_uis = []

    @property
    def timeline_uis(self):
        return self._timeline_uis
