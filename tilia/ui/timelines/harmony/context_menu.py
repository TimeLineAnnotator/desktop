from tilia.ui import actions
from tilia.ui.actions import TiliaAction
from tilia.ui.menus import TiliaMenu, MenuItemKind
from tilia.ui.timelines.base.context_menu import TimelineUIContextMenu


class ModeContextMenu(TiliaMenu):
    name = "Mode"
    items = [
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_EDIT),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_COPY),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_PASTE),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_ELEMENT_DELETE),
    ]


class HarmonyContextMenu(TiliaMenu):
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
        (MenuItemKind.ACTION, TiliaAction.TIMELINE_HEIGHT_SET),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.ACTION, TiliaAction.HARMONY_TIMELINE_SHOW_KEYS),
        (MenuItemKind.ACTION, TiliaAction.HARMONY_TIMELINE_HIDE_KEYS),
    ]

    def __init__(self, timeline_ui):
        if timeline_ui.get_data("visible_level_count") == 1:
            actions.taction_to_qaction[
                TiliaAction.HARMONY_TIMELINE_HIDE_KEYS
            ].setVisible(False)
            actions.taction_to_qaction[
                TiliaAction.HARMONY_TIMELINE_SHOW_KEYS
            ].setVisible(True)
        else:
            actions.taction_to_qaction[
                TiliaAction.HARMONY_TIMELINE_HIDE_KEYS
            ].setVisible(True)
            actions.taction_to_qaction[
                TiliaAction.HARMONY_TIMELINE_SHOW_KEYS
            ].setVisible(False)
        super().__init__(timeline_ui)
