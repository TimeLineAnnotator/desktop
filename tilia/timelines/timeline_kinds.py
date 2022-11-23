from enum import Enum


class TimelineKind(Enum):
    HIERARCHY_TIMELINE = "hierarchy"
    MARKER_TIMELINE = "marker"
    BEAT_TIMELINE = "beat"
    RANGE_TIMELINE = "range"
    SLIDER_TIMELINE = "slider"

IMPLEMENTED_TIMELINE_KINDS = ['HIERARCHY_TIMELINE', 'SLIDER_TIMELINE']
