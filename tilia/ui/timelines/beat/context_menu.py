from __future__ import annotations

from typing import TYPE_CHECKING

from tilia.ui.commands import get_qaction
from tilia.ui.menus import MenuItemKind
from tilia.ui.timelines.base.context_menus import (
    TimelineUIContextMenu,
    TimelineUIElementContextMenu,
)

if TYPE_CHECKING:
    from tilia.ui.timelines.beat.beat_unit import BeatUnitUI


class BeatContextMenu(TimelineUIElementContextMenu):
    name = "Beat"
    items = [
        (MenuItemKind.COMMAND, "timeline.element.inspect"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.beat.set_measure_number"),
        (MenuItemKind.COMMAND, "timeline.beat.reset_measure_number"),
        (MenuItemKind.COMMAND, "timeline.beat.distribute"),
        (MenuItemKind.COMMAND, "timeline.beat.set_amount_in_measure"),
        (MenuItemKind.COMMAND, "timeline.beat.set_beat_unit"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.component.copy"),
        (MenuItemKind.COMMAND, "timeline.component.paste"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.component.delete"),
    ]


class BeatUnitContextMenu(TimelineUIElementContextMenu):
    name = "Beat unit"
    items = [
        (MenuItemKind.COMMAND, "timeline.beat.set_beat_unit"),
        (MenuItemKind.SEPARATOR, None),
        (MenuItemKind.COMMAND, "timeline.component.delete"),
    ]

    def __init__(self, element: BeatUnitUI) -> None:
        super().__init__(element)
        # A measure can hold several beat units after its barlines move. Only
        # the first has a label, so the others are removed from here.
        measure_index = element.active_measure_index
        timeline = element.timeline_ui.timeline
        if (
            measure_index is not None
            and measure_index < timeline.measure_count
            and timeline.get_measure_meter(measure_index).is_conflicting
        ):
            self.insertAction(
                self.actions()[1],
                get_qaction("timeline.beat.remove_other_beat_units"),
            )


class BeatTimelineUIContextMenu(TimelineUIContextMenu):
    name = "Beat timeline"
    items = [
        (MenuItemKind, "timeline.set_name"),
        (MenuItemKind.COMMAND, "timeline.beat.set_pattern"),
        (MenuItemKind.COMMAND, "timeline.beat.toggle_time_signatures"),
    ]
