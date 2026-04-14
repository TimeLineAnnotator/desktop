from tilia.ui.menus import MenuItemKind
from tilia.ui.timelines.base.context_menus import (
    TimelineUIContextMenu,
    TimelineUIElementContextMenu,
)


class BeatContextMenu(TimelineUIElementContextMenu):
    name = "Beat"
    items = [
        (MenuItemKind.COMMAND, "timeline.element.inspect"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.beat.set_measure_number"),
        (MenuItemKind.COMMAND, "timeline.beat.reset_measure_number"),
        (MenuItemKind.COMMAND, "timeline.beat.distribute"),
        (MenuItemKind.COMMAND, "timeline.beat.set_amount_in_measure"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.component.copy"),
        (MenuItemKind.COMMAND, "timeline.component.paste"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.component.delete"),
    ]


class BeatTimelineUIContextMenu(TimelineUIContextMenu):
    name = "Beat timeline"
    items = [(MenuItemKind, "timeline.set_name")]
