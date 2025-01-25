from tilia.ui.actions import TiliaAction
from tilia.ui.menus import MenuItemKind
from tilia.ui.timelines.base.context_menus import TimelineUIElementContextMenu


class NoteContextMenu(TimelineUIElementContextMenu):
    name = "Note"
    items = [
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_INSPECT),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_COLOR_SET),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_COLOR_RESET),
    ]


class ScoreTimelineUIContextMenu(TimelineUIElementContextMenu):
    name = "Beat timeline"
    items = [(MenuItemKind, TiliaAction.TIMELINE_NAME_SET)]
