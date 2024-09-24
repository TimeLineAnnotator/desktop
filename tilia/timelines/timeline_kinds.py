from enum import Enum


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
