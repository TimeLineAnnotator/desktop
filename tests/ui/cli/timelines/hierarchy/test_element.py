from __future__ import annotations
from typing import TYPE_CHECKING

from tilia import settings
from tilia.ui.cli.timelines.base import TimelineUIElement

if TYPE_CHECKING:
    from tilia.timelines.hierarchy.components import Hierarchy


class HierarchyUI(TimelineUIElement):
    DEFAULT_COLORS = settings.get("hierarchy_timeline", "hierarchy_default_colors")

    def __init__(
        self, component: Hierarchy, label: str = "", color: str = "", **kwargs
    ):
        super().__init__(component)
        self.label = label
        self.color = color or self.get_color(component.level)

    def get_color(self, level: int) -> str:
        return self.DEFAULT_COLORS[level % len(self.DEFAULT_COLORS)]
