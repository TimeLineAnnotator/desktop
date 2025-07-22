from __future__ import annotations

from tilia.ui.menus import MenuItemKind
from tilia.ui.timelines.base.context_menus import TimelineUIElementContextMenu


DEFAULT_ITEMS = [
    (MenuItemKind.ACTION, "timeline_element_inspect"),
    (MenuItemKind.SEPARATOR, None),
    (MenuItemKind.ACTION, "hierarchy_increase_level"),
    (MenuItemKind.ACTION, "hierarchy_decrease_level"),
    (MenuItemKind.ACTION, "timeline_element_color_set"),
    (MenuItemKind.ACTION, "timeline_element_color_reset"),
    (MenuItemKind.SEPARATOR, None),
    (MenuItemKind.ACTION, "timeline_element_copy"),
    (MenuItemKind.ACTION, "timeline_element_paste"),
    (MenuItemKind.ACTION, "timeline_element_paste_complete"),
    (MenuItemKind.SEPARATOR, None),
    (MenuItemKind.ACTION, "timeline_element_export_audio"),
    (MenuItemKind.ACTION, "timeline_element_delete"),
]


class HierarchyContextMenu(TimelineUIElementContextMenu):
    title = "Hierarchy"

    def __init__(self, element):
        self.items = DEFAULT_ITEMS.copy()
        if not element.has_pre_start:
            self.items.insert(6, (MenuItemKind.ACTION, "hierarchy_add_pre_start"))

        if not element.has_post_end:
            self.items.insert(6, (MenuItemKind.ACTION, "hierarchy_add_post_end"))

        super().__init__(element)
