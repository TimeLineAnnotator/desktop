from tilia.ui.actions import TiliaAction
from tilia.ui.menus import MenuItemKind, TiliaMenu


class TimelineUIContextMenu(TiliaMenu):
    title = "Timeline"
    items = [
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_NAME_SET),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_HEIGHT_SET),
    ]

    def __init__(self, timeline_ui):
        super().__init__()
        self.timeline_ui = timeline_ui


class TimelineUIElementContextMenu(TiliaMenu):
    title = "TimelineElement"
    items = []

    def __init__(self, element):
        super().__init__()
        self.element = element
