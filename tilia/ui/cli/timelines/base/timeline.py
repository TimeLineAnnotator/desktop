from tilia.timelines.common import TimelineComponent
from tilia.timelines.component_kinds import ComponentKind


class TimelineUI:
    def __init__(self):
        pass

    def get_ui_for_component(
        self, component_kind: ComponentKind, component: TimelineComponent, **kwargs
    ):
        ...
