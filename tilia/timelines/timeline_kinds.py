from enum import Enum

from tilia.timelines.base.timeline import Timeline


class TimelineKind(Enum):
    PDF_TIMELINE = "PDF_TIMELINE"
    HARMONY_TIMELINE = "HARMONY_TIMELINE"
    HIERARCHY_TIMELINE = "HIERARCHY_TIMELINE"
    MARKER_TIMELINE = "MARKER_TIMELINE"
    BEAT_TIMELINE = "BEAT_TIMELINE"
    SLIDER_TIMELINE = "SLIDER_TIMELINE"
    AUDIOWAVE_TIMELINE = "AUDIOWAVE_TIMELINE"


COLORED_COMPONENTS = [TimelineKind.MARKER_TIMELINE, TimelineKind.HIERARCHY_TIMELINE]

NOT_SLIDER = [
    TimelineKind.HIERARCHY_TIMELINE,
    TimelineKind.MARKER_TIMELINE,
    TimelineKind.BEAT_TIMELINE,
    TimelineKind.HARMONY_TIMELINE,
    TimelineKind.PDF_TIMELINE,
    TimelineKind.AUDIOWAVE_TIMELINE,
]
ALL = list(TimelineKind)


def get_timeline_kind_from_string(string):
    string = string.upper()
    if not string.endswith("_TIMELINE"):
        string = string + "_TIMELINE"

    return TimelineKind(string)


def get_timeline_class_from_kind(kind: TimelineKind) -> type[Timeline]:
    from tilia.timelines.marker.timeline import MarkerTimeline
    from tilia.timelines.beat.timeline import BeatTimeline
    from tilia.timelines.hierarchy.timeline import HierarchyTimeline
    from tilia.timelines.pdf.timeline import PdfTimeline
    from tilia.timelines.slider.timeline import SliderTimeline
    from tilia.timelines.audiowave.timeline import AudioWaveTimeline
    from tilia.timelines.harmony.timeline import HarmonyTimeline

    return {
        TimelineKind.MARKER_TIMELINE: MarkerTimeline,
        TimelineKind.BEAT_TIMELINE: BeatTimeline,
        TimelineKind.HIERARCHY_TIMELINE: HierarchyTimeline,
        TimelineKind.PDF_TIMELINE: PdfTimeline,
        TimelineKind.SLIDER_TIMELINE: SliderTimeline,
        TimelineKind.AUDIOWAVE_TIMELINE: AudioWaveTimeline,
        TimelineKind.HARMONY_TIMELINE: HarmonyTimeline,
    }[kind]
