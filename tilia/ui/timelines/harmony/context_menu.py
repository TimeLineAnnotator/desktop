from tilia.ui import actions
from tilia.ui.menus import MenuItemKind
from tilia.ui.timelines.base.context_menus import (
    TimelineUIContextMenu,
    TimelineUIElementContextMenu,
)


class ModeContextMenu(TimelineUIElementContextMenu):
    name = "Mode"
    items = [
        (MenuItemKind.ACTION, "timeline_element_edit"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "timeline_element_copy"),
        (MenuItemKind.ACTION, "timeline_element_paste"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "timeline_element_delete"),
    ]


class HarmonyContextMenu(TimelineUIElementContextMenu):
    name = "Harmony"
    items = [
        (MenuItemKind.ACTION, "timeline_element_edit"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "timeline_element_copy"),
        (MenuItemKind.ACTION, "timeline_element_paste"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "harmony_display_as_roman_numeral"),
        (MenuItemKind.ACTION, "harmony_display_as_chord_symbol"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "timeline_element_delete"),
    ]


class HarmonyTimelineUIContextMenu(TimelineUIContextMenu):
    name = "Harmony timeline"
    items = [
        (MenuItemKind.ACTION, "timeline_name_set"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, "harmony_timeline_show_keys"),
        (MenuItemKind.ACTION, "harmony_timeline_hide_keys"),
    ]

    def __init__(self, timeline_ui):
        hide_keys_action = actions.get_qaction("harmony_timeline_hide_keys")
        show_keys_action = actions.get_qaction("harmony_timeline_show_keys")
        if timeline_ui.get_data("visible_level_count") == 1:
            hide_keys_action.setVisible(False)
            show_keys_action.setVisible(True)
        else:
            hide_keys_action.setVisible(True)
            show_keys_action.setVisible(False)
        super().__init__(timeline_ui)
