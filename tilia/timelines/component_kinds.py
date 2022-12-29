from enum import auto, StrEnum


class ComponentKind(StrEnum):
    BEAT = auto()
    MARKER = auto()
    HIERARCHY = auto()


def get_component_class_by_kind(kind: ComponentKind):
    from tilia.timelines.hierarchy.components import Hierarchy
    from tilia.timelines.marker.components import Marker
    from tilia.timelines.beat.components import Beat

    kind_to_class_dict = {
        ComponentKind.HIERARCHY: Hierarchy,
        ComponentKind.MARKER: Marker,
        ComponentKind.BEAT: Beat,
    }

    return kind_to_class_dict[kind]
