from __future__ import annotations

from tilia.ui.menus import MenuItemKind
from tilia.ui.timelines.base.context_menus import TimelineUIElementContextMenu

DEFAULT_ITEMS = [
    (MenuItemKind.COMMAND, "timeline.element.inspect"),
    (MenuItemKind.SEPARATOR, None),
    (MenuItemKind.COMMAND, "timeline.hierarchy.increase_level"),
    (MenuItemKind.COMMAND, "timeline.hierarchy.decrease_level"),
    (MenuItemKind.COMMAND, "timeline.component.set_color"),
    (MenuItemKind.COMMAND, "timeline.component.reset_color"),
    (MenuItemKind.SEPARATOR, None),
    (MenuItemKind.COMMAND, "timeline.component.copy"),
    (MenuItemKind.COMMAND, "timeline.component.paste"),
    (MenuItemKind.COMMAND, "timeline.component.paste_complete"),
    (MenuItemKind.SEPARATOR, None),
    (MenuItemKind.COMMAND, "timeline.hierarchy.export_audio"),
    (MenuItemKind.COMMAND, "timeline.component.delete"),
]


class HierarchyContextMenu(TimelineUIElementContextMenu):
    title = "Hierarchy"

    def __init__(self, element):
        self.items = DEFAULT_ITEMS.copy()
        if not element.has_pre_start:
            self.items.insert(
                6, (MenuItemKind.COMMAND, "timeline.hierarchy.add_pre_start")
            )

        if not element.has_post_end:
            self.items.insert(
                6, (MenuItemKind.COMMAND, "timeline.hierarchy.add_post_end")
            )

        super().__init__(element)
