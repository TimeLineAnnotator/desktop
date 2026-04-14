from tilia.ui.menus import MenuItemKind
from tilia.ui.timelines.base.context_menus import (
    TimelineUIContextMenu,
    TimelineUIElementContextMenu,
)


class MarkerContextMenu(TimelineUIElementContextMenu):
    name = "Marker"
    items = [
        (MenuItemKind.COMMAND, "timeline.element.inspect"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.component.set_color"),
        (MenuItemKind.COMMAND, "timeline.component.reset_color"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.component.copy"),
        (MenuItemKind.COMMAND, "timeline.component.paste"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.component.delete"),
    ]


class MarkerTimelineUIContextMenu(TimelineUIContextMenu):
    name = "Marker timeline"
    items = [(MenuItemKind.COMMAND, "timeline.set_name")]
