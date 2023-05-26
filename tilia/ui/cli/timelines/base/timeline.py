from tilia.timelines.common import TimelineComponent
from tilia.timelines.component_kinds import ComponentKind


class TimelineUI:
    def __init__(self, name: str, *args, display_position: int, **kwargs):
        self.name = name
        self.display_position = display_position

    def get_ui_for_component(
        self, component_kind: ComponentKind, component: TimelineComponent, **kwargs
    ):
        ...
