from tilia.timelines.common import TimelineComponent
from tilia.timelines.component_kinds import ComponentKind


class TimelineUI:
    ELEMENT_CLASS = None

    def __init__(self, name: str, *args, display_position: int, **kwargs):
        self.name = name
        self.display_position = display_position
        self.elements = set()

    def get_ui_for_component(
        self, _: ComponentKind, component: TimelineComponent, **kwargs
    ):
        return self.create_element(component, **kwargs)

    def create_element(self, component: TimelineComponent, **kwargs):
        element = self.ELEMENT_CLASS.create(component, **kwargs)
        self.elements.add(element)
        return element
