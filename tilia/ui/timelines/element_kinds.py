from tilia.timelines.component_kinds import ComponentKind


def get_element_class_by_kind(kind: ComponentKind):
    from tilia.ui.timelines.hierarchy.element import HierarchyUI
    from tilia.ui.timelines.marker.element import MarkerUI
    from tilia.ui.timelines.beat.element import BeatUI
    from tilia.ui.timelines.harmony.elements import HarmonyUI, ModeUI
    from tilia.ui.timelines.audiowave.element import AmplitudeBarUI
    from tilia.ui.timelines.score.element import (
        NoteUI,
        StaffUI,
        ClefUI,
        BarLineUI,
        TimeSignatureUI,
        KeySignatureUI,
        ScoreSVGUI,
    )

    kind_to_class_dict = {
        ComponentKind.HIERARCHY: HierarchyUI,
        ComponentKind.MARKER: MarkerUI,
        ComponentKind.BEAT: BeatUI,
        ComponentKind.HARMONY: HarmonyUI,
        ComponentKind.MODE: ModeUI,
        ComponentKind.AUDIOWAVE: AmplitudeBarUI,
        ComponentKind.NOTE: NoteUI,
        ComponentKind.STAFF: StaffUI,
        ComponentKind.CLEF: ClefUI,
        ComponentKind.BAR_LINE: BarLineUI,
        ComponentKind.TIME_SIGNATURE: TimeSignatureUI,
        ComponentKind.KEY_SIGNATURE: KeySignatureUI,
        ComponentKind.SCORE_SVG: ScoreSVGUI,
    }

    return kind_to_class_dict[kind]
