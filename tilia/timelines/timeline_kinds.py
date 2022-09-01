from enum import Enum


class TimelineKind(Enum):
    HIERARCHY_TIMELINE = "hierarchy"
    MARKER_TIMELINE = "marker"
    RANGE_TIMELINE = "range"
    SLIDER_TIMELINE = "slider"
