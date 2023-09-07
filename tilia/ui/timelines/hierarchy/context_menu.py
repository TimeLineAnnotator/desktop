from __future__ import annotations

from typing import Callable

from tilia.ui.actions import TiliaAction
from tilia.ui.menus import TiliaMenu, MenuItemKind
from tilia.ui.timelines.base.context_menu import TimelineUIContextMenu


class HierarchyContextMenu(TimelineUIContextMenu):
    title = "Hierarchy"
    items = [
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
        (MenuItemKind.ACTION, TiliaAction.HIERARCHY_DELETE),
    ]

    def __init__(
        self, timeline_ui, has_pre_start: Callable[[], bool], has_post_end: Callable[[], bool]
    ):
        super().__init__(timeline_ui)
        if not has_pre_start():
            self.items.insert(
                6, (MenuItemKind.ACTION, TiliaAction.HIERARCHY_ADD_PRE_START)
            )

        if not has_post_end():
            self.items.insert(
                6, (MenuItemKind.ACTION, TiliaAction.HIERARCHY_ADD_POST_END)
            )
