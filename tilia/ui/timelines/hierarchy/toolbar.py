from tilia.ui.timelines.toolbar import TimelineToolbar


class HierarchyTimelineToolbar(TimelineToolbar):
    ACTIONS = [
        "hierarchy_split",
        "hierarchy_merge",
        "hierarchy_group",
        "hierarchy_increase_level",
        "hierarchy_decrease_level",
        "hierarchy_create_child",
    ]
