from enum import auto, StrEnum


class ComponentKind(StrEnum):
    MARKER = auto()
    HIERARCHY = auto()


def get_component_class_by_kind(kind: ComponentKind):
    from tilia.timelines.hierarchy.components import Hierarchy
    from tilia.timelines.marker.components import Marker

    kind_to_class_dict = {
        ComponentKind.HIERARCHY: Hierarchy,
        ComponentKind.MARKER: Marker
    }

    return kind_to_class_dict[kind]
