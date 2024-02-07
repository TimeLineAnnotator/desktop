from __future__ import annotations
from typing import Protocol, TYPE_CHECKING, Optional

from tilia.timelines.timeline_kinds import TimelineKind

if TYPE_CHECKING:
    from tilia.ui.cli.timelines.base import TimelineUIElement
    from tilia.timelines.common import TimelineComponent
    from tilia.timelines.component_kinds import ComponentKind


class TimelineUI(Protocol):
    TIMELINE_KIND: TimelineKind
    ELEMENT_CLASS: Optional[TimelineUIElement]
    name: str
    is_visible: bool
    height: int
    display_position: int

    def get_ui_for_component(
        self, component_kind: ComponentKind, component: TimelineComponent, **kwargs
    ):
        ...

    def create_element(self, component: TimelineComponent, **kwargs):
        ...
