from __future__ import annotations

from enum import auto, Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tilia.timelines.base.component import TimelineComponent


class ComponentKind(Enum):
    PDF_MARKER = auto()
    MODE = auto()
    HARMONY = auto()
    BEAT = auto()
    MARKER = auto()
    NOTE = auto()
    HIERARCHY = auto()
    AUDIOWAVE = auto()
    STAFF = auto()
    CLEF = auto()


def get_component_class_by_kind(kind: ComponentKind) -> type[TimelineComponent]:
    from tilia.timelines.hierarchy.components import Hierarchy
    from tilia.timelines.marker.components import Marker
    from tilia.timelines.beat.components import Beat
    from tilia.timelines.harmony.components import Harmony, Mode
    from tilia.timelines.pdf.components import PdfMarker
    from tilia.timelines.audiowave.components import AmplitudeBar
    from tilia.timelines.score.components import Note, Staff, Clef

    kind_to_class_dict = {
        ComponentKind.HIERARCHY: Hierarchy,
        ComponentKind.MARKER: Marker,
        ComponentKind.BEAT: Beat,
        ComponentKind.HARMONY: Harmony,
        ComponentKind.NOTE: Note,
        ComponentKind.MODE: Mode,
        ComponentKind.PDF_MARKER: PdfMarker,
        ComponentKind.AUDIOWAVE: AmplitudeBar,
        ComponentKind.STAFF: Staff,
        ComponentKind.CLEF: Clef,
    }

    return kind_to_class_dict[kind]
