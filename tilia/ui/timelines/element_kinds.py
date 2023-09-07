from tilia.timelines.component_kinds import ComponentKind


def get_element_class_by_kind(kind: ComponentKind):
    from tilia.ui.timelines.hierarchy.element import HierarchyUI
    from tilia.ui.timelines.marker.element import MarkerUI
    from tilia.ui.timelines.beat.element import BeatUI
    from tilia.ui.timelines.harmony.elements import HarmonyUI, ModeUI

    kind_to_class_dict = {
        ComponentKind.HIERARCHY: HierarchyUI,
        ComponentKind.MARKER: MarkerUI,
        ComponentKind.BEAT: BeatUI,
        ComponentKind.HARMONY: HarmonyUI,
        ComponentKind.MODE: ModeUI,
    }

    return kind_to_class_dict[kind]
