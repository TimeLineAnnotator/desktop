from tilia.ui.actions import TiliaAction
from tilia.ui.menus import TiliaMenu, MenuItemKind
from tilia.ui.timelines.base.context_menu import TimelineUIContextMenu


class MarkerContextMenu(TimelineUIContextMenu):
    name = "Marker"
    items = [
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_INSPECT),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_COLOR_SET),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_COLOR_RESET),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_COPY),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_PASTE),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_DELETE),
    ]
