from __future__ import annotations

from tilia.ui.actions import TiliaAction
from tilia.ui.menus import MenuItemKind
from tilia.ui.timelines.base.context_menus import TimelineUIElementContextMenu


DEFAULT_ITEMS = [
    (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_INSPECT),
    (MenuItemKind.SEPARATOR, None),
    (MenuItemKind.ACTION, TiliaAction.HIERARCHY_INCREASE_LEVEL),
    (MenuItemKind.ACTION, TiliaAction.HIERARCHY_DECREASE_LEVEL),
    (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_COLOR_SET),
    (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_COLOR_RESET),
    (MenuItemKind.SEPARATOR, None),
    (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_COPY),
    (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_PASTE),
    (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_PASTE_COMPLETE),
    (MenuItemKind.SEPARATOR, None),
    (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_EXPORT_AUDIO),
    (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_DELETE),
]


class HierarchyContextMenu(TimelineUIElementContextMenu):
    title = "Hierarchy"

    def __init__(self, element):
        self.items = DEFAULT_ITEMS.copy()
        if not element.has_pre_start:
            self.items.insert(
                6, (MenuItemKind.ACTION, TiliaAction.HIERARCHY_ADD_PRE_START)
            )

        if not element.has_post_end:
            self.items.insert(
                6, (MenuItemKind.ACTION, TiliaAction.HIERARCHY_ADD_POST_END)
            )

        super().__init__(element)
