from enum import Enum, auto
import importlib


class ComponentKind(Enum):
    HIERARCHY = auto()


def get_component_class_by_kind(kind: ComponentKind):
    from tilia.timelines.hierarchy.components import Hierarchy

    kind_to_class_dict = {ComponentKind.HIERARCHY: Hierarchy}

    return kind_to_class_dict[kind]
