from tilia.ui.menus import MenuItemKind
from tilia.ui.timelines.base.context_menus import TimelineUIElementContextMenu


class NoteContextMenu(TimelineUIElementContextMenu):
    name = "Note"
    items = [
        (MenuItemKind.ACTION, "timeline_element_inspect"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "timeline_element_color_set"),
        (MenuItemKind.ACTION, "timeline_element_color_reset"),
    ]


class ScoreTimelineUIContextMenu(TimelineUIElementContextMenu):
    name = "Beat timeline"
    items = [(MenuItemKind, "timeline_name_set")]
