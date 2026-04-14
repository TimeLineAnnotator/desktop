from tilia.ui.menus import MenuItemKind
from tilia.ui.timelines.base.context_menus import (
    TimelineUIContextMenu,
    TimelineUIElementContextMenu,
)


class PdfMarkerContextMenu(TimelineUIElementContextMenu):
    name = "PDF Marker"
    items = [
        (MenuItemKind.COMMAND, "timeline.element.inspect"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.component.copy"),
        (MenuItemKind.COMMAND, "timeline.component.paste"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.component.delete"),
    ]


class PdfTimelineUIContextMenu(TimelineUIContextMenu):
    name = "PDF timeline"
    items = [(MenuItemKind, "timeline.set_name")]
