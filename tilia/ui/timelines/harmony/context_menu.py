from tilia.ui import commands
from tilia.ui.menus import MenuItemKind
from tilia.ui.timelines.base.context_menus import (
    TimelineUIContextMenu,
    TimelineUIElementContextMenu,
)


class ModeContextMenu(TimelineUIElementContextMenu):
    name = "Mode"
    items = [
        (MenuItemKind.COMMAND, "timeline.element.inspect"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.component.copy"),
        (MenuItemKind.COMMAND, "timeline.component.paste"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.component.delete"),
    ]


class HarmonyContextMenu(TimelineUIElementContextMenu):
    name = "Harmony"
    items = [
        (MenuItemKind.COMMAND, "timeline.element.inspect"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.component.copy"),
        (MenuItemKind.COMMAND, "timeline.component.paste"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.harmony.component.display_as_roman"),
        (MenuItemKind.COMMAND, "timeline.harmony.component.display_as_letter"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.component.delete"),
    ]


class HarmonyTimelineUIContextMenu(TimelineUIContextMenu):
    name = "Harmony timeline"
    items = [
        (MenuItemKind.COMMAND, "timeline.set_name"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.harmony.show_keys"),
        (MenuItemKind.COMMAND, "timeline.harmony.hide_keys"),
    ]

    def __init__(self, timeline_ui, x: int, y: int):
        hide_keys_action = commands.get_qaction("timeline.harmony.hide_keys")
        show_keys_action = commands.get_qaction("timeline.harmony.show_keys")
        if timeline_ui.get_data("visible_level_count") == 1:
            hide_keys_action.setVisible(False)
            show_keys_action.setVisible(True)
        else:
            hide_keys_action.setVisible(True)
            show_keys_action.setVisible(False)
        super().__init__(timeline_ui, x, y)
