from tilia.ui.actions import TiliaAction
from tilia.ui.timelines.toolbar import TimelineToolbar


class HierarchyTimelineToolbar(TimelineToolbar):
    ACTIONS = [
        TiliaAction.HIERARCHY_SPLIT,
        TiliaAction.HIERARCHY_MERGE,
        TiliaAction.HIERARCHY_GROUP,
        TiliaAction.HIERARCHY_INCREASE_LEVEL,
        TiliaAction.HIERARCHY_DECREASE_LEVEL,
        TiliaAction.HIERARCHY_CREATE_CHILD,
        TiliaAction.HIERARCHY_DELETE,
    ]
