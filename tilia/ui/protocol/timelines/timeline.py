from __future__ import annotations
from typing import Protocol, TYPE_CHECKING

from tilia.timelines.timeline_kinds import TimelineKind

if TYPE_CHECKING:
    from tilia.timelines.common import TimelineComponent
    from tilia.timelines.component_kinds import ComponentKind


class TimelineUI(Protocol):
    TIMELINE_KIND: TimelineKind
    name: str
    is_visible: bool
    height: int
    display_position: int

    def get_ui_for_component(
        self, component_kind: ComponentKind, component: TimelineComponent, **kwargs
    ):
        ...
