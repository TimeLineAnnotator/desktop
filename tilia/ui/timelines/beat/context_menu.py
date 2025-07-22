from tilia.ui.menus import MenuItemKind
from tilia.ui.timelines.base.context_menus import (
    TimelineUIElementContextMenu,
    TimelineUIContextMenu,
)


class BeatContextMenu(TimelineUIElementContextMenu):
    name = "Beat"
    items = [
        (MenuItemKind.ACTION, "timeline_element_inspect"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "beat_set_measure_number"),
        (MenuItemKind.ACTION, "beat_reset_measure_number"),
        (MenuItemKind.ACTION, "beat_distribute"),
        (MenuItemKind.ACTION, "beat_set_amount_in_measure"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "timeline_element_copy"),
        (MenuItemKind.ACTION, "timeline_element_paste"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "timeline_element_delete"),
    ]


class BeatTimelineUIContextMenu(TimelineUIContextMenu):
    name = "Beat timeline"
    items = [(MenuItemKind, "timeline_name_set")]
