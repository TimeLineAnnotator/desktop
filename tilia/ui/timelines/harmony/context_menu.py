from tilia.ui import actions
from tilia.ui.actions import TiliaAction
from tilia.ui.menus import MenuItemKind
from tilia.ui.timelines.base.context_menus import (
    TimelineUIContextMenu,
    TimelineUIElementContextMenu,
)


class ModeContextMenu(TimelineUIElementContextMenu):
    name = "Mode"
    items = [
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_EDIT),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_COPY),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_PASTE),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_DELETE),
    ]


class HarmonyContextMenu(TimelineUIElementContextMenu):
    name = "Harmony"
    items = [
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_EDIT),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_COPY),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_PASTE),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.HARMONY_DISPLAY_AS_ROMAN_NUMERAL),
        (MenuItemKind.ACTION, TiliaAction.HARMONY_DISPLAY_AS_CHORD_SYMBOL),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_DELETE),
    ]


class HarmonyTimelineUIContextMenu(TimelineUIContextMenu):
    name = "Harmony timeline"
    items = [
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_NAME_SET),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.HARMONY_TIMELINE_SHOW_KEYS),
        (MenuItemKind.ACTION, TiliaAction.HARMONY_TIMELINE_HIDE_KEYS),
    ]

    def __init__(self, timeline_ui):
        hide_keys_action = actions.get_qaction(TiliaAction.HARMONY_TIMELINE_HIDE_KEYS)
        show_keys_action = actions.get_qaction(TiliaAction.HARMONY_TIMELINE_SHOW_KEYS)
        if timeline_ui.get_data("visible_level_count") == 1:
            hide_keys_action.setVisible(False)
            show_keys_action.setVisible(True)
        else:
            hide_keys_action.setVisible(True)
            show_keys_action.setVisible(False)
        super().__init__(timeline_ui)
