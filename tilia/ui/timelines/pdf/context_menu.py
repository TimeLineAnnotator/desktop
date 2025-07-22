from tilia.ui.menus import MenuItemKind
from tilia.ui.timelines.base.context_menus import (
    TimelineUIElementContextMenu,
    TimelineUIContextMenu,
)


class PdfMarkerContextMenu(TimelineUIElementContextMenu):
    name = "PDF Marker"
    items = [
        (MenuItemKind.ACTION, "timeline_element_inspect"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "timeline_element_copy"),
        (MenuItemKind.ACTION, "timeline_element_paste"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "timeline_element_delete"),
    ]


class PdfTimelineUIContextMenu(TimelineUIContextMenu):
    name = "PDF timeline"
    items = [(MenuItemKind, "timeline_name_set")]
