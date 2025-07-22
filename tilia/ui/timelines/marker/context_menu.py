from tilia.ui.menus import MenuItemKind
from tilia.ui.timelines.base.context_menus import (
    TimelineUIElementContextMenu,
    TimelineUIContextMenu,
)


class MarkerContextMenu(TimelineUIElementContextMenu):
    name = "Marker"
    items = [
        (MenuItemKind.ACTION, "timeline_element_inspect"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "timeline_element_color_set"),
        (MenuItemKind.ACTION, "timeline_element_color_reset"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "timeline_element_copy"),
        (MenuItemKind.ACTION, "timeline_element_paste"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "timeline_element_delete"),
    ]


class MarkerTimelineUIContextMenu(TimelineUIContextMenu):
    name = "Marker timeline"
    items = [(MenuItemKind.ACTION, "timeline_name_set")]
