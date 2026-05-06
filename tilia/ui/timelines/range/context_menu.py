from __future__ import annotations

from typing import TYPE_CHECKING, Callable, cast

from PySide6.QtCore import QPoint
from PySide6.QtGui import QAction

from tilia.log import logger
from tilia.ui import commands
from tilia.ui.menus import MenuItemKind
from tilia.ui.timelines.base.context_menus import (
    TimelineUIContextMenu,
    TimelineUIElementContextMenu,
)

if TYPE_CHECKING:
    from tilia.ui.timelines.base.timeline import TimelineUI
    from tilia.ui.timelines.range.element import RangeUI


class RangeTimelineContextMenu(TimelineUIContextMenu):
    # Drops `timeline.set_height` (height is computed from row count for range
    # timelines; "Set default row height" plays that role instead).
    items = [(MenuItemKind.COMMAND, "timeline.set_name")]

    def __init__(self, timeline_ui: TimelineUI, x: int, y: int):
        super().__init__(timeline_ui, x, y)

        from tilia.ui.timelines.range import RangeTimelineUI

        self.timeline_ui = cast(RangeTimelineUI, self.timeline_ui)

        local_y = self.timeline_ui.view.mapFromGlobal(QPoint(x, y)).y()
        self.row = self.timeline_ui.get_row_by_y(local_y)

        self.addSeparator()
        self._add_row_actions()

    def _add_timeline_actions(self) -> None:
        # Slot "Set default row height" alongside "Set name" at the top,
        # before the move-up/down + delete/clear block.
        set_default_row_height = QAction(self)
        set_default_row_height.setObjectName("set default row height")
        set_default_row_height.setText("Set default row height")
        set_default_row_height.triggered.connect(
            lambda: commands.execute("timeline.range.set_row_height")
        )
        self.addAction(set_default_row_height)

        super()._add_timeline_actions()

    def _add_row_actions(self) -> None:
        def add_action(text: str, callback: Callable[[], None]) -> None:
            action = QAction(self)
            action.setObjectName(text.lower())
            action.setText(text)
            action.triggered.connect(callback)
            self.addAction(action)

        add_action("Add row above", self.on_add_row_above)
        add_action("Add row below", self.on_add_row_below)

        if self.row is None:
            return

        add_action("Rename row", self.on_rename_row)
        add_action("Set row color", self.on_set_row_color)
        if self.row.color is not None:
            add_action("Reset row color", self.on_reset_row_color)
        add_action("Set height for this row", self.on_set_row_height_for_row)
        if self.row.height is not None:
            add_action("Reset row height", self.on_reset_row_height_for_row)
        row_idx = self.timeline_ui.timeline.row_index(self.row)
        if row_idx is None:
            # row was found by y-coordinate but isn't in timeline.rows — stale
            # UI reference. Skip the move actions so we never execute against a
            # detached row, and surface the divergence in the log.
            logger.error(
                "RangeTimelineContextMenu: row %r not found in timeline.rows; "
                "move/remove actions skipped.",
                self.row,
            )
        else:
            if row_idx > 0:
                add_action("Move row up", self.on_move_row_up)
            if row_idx < self.timeline_ui.timeline.row_count - 1:
                add_action("Move row down", self.on_move_row_down)
        if self.timeline_ui.timeline.row_count > 1:
            add_action("Remove row", self.on_remove_row)

    def on_add_row_above(self) -> None:
        idx = self.timeline_ui.row_index(self.row.id) if self.row is not None else 0
        commands.execute("timeline.range.add_row", idx)

    def on_add_row_below(self) -> None:
        idx = (
            self.timeline_ui.row_index(self.row.id) + 1
            if self.row is not None
            else self.timeline_ui.timeline.row_count
        )
        commands.execute("timeline.range.add_row", idx)

    def on_rename_row(self) -> None:
        commands.execute("timeline.range.rename_row", row=self.row)

    def on_set_row_color(self) -> None:
        commands.execute("timeline.range.set_row_color", row=self.row, color=None)

    def on_reset_row_color(self) -> None:
        commands.execute("timeline.range.reset_row_color", row=self.row)

    def on_set_row_height_for_row(self) -> None:
        commands.execute("timeline.range.set_row_height_for_row", row=self.row)

    def on_reset_row_height_for_row(self) -> None:
        commands.execute("timeline.range.reset_row_height_for_row", row=self.row)

    def on_move_row_up(self) -> None:
        commands.execute("timeline.range.move_row_up", row=self.row)

    def on_move_row_down(self) -> None:
        commands.execute("timeline.range.move_row_down", row=self.row)

    def on_remove_row(self) -> None:
        commands.execute("timeline.range.remove_row", row=self.row)


class RangeContextMenu(TimelineUIElementContextMenu):
    title = "Range"

    def __init__(self, element: RangeUI):
        items: list = [
            (MenuItemKind.COMMAND, "timeline.element.inspect"),
            (MenuItemKind.SEPARATOR, None),
            (MenuItemKind.COMMAND, "timeline.component.set_color"),
            (MenuItemKind.COMMAND, "timeline.component.reset_color"),
        ]

        timeline_ui = element.timeline_ui
        selected = timeline_ui.selected_components
        # Join/merge with selected: only when ≥2 ranges in the same row
        # are selected.
        if len(selected) >= 2 and len({c.row_id for c in selected}) == 1:
            items += [
                (MenuItemKind.SEPARATOR, None),
                (MenuItemKind.COMMAND, "timeline.range.join_ranges"),
                (MenuItemKind.COMMAND, "timeline.range.merge_ranges"),
            ]

        items += [
            (MenuItemKind.SEPARATOR, None),
            (MenuItemKind.COMMAND, "timeline.range.split_range"),
        ]

        row_idx = timeline_ui.row_index(element.get_data("row_id"))
        row_count = timeline_ui.timeline.row_count
        move_items = []
        if row_idx is not None and row_idx > 0:
            move_items.append(
                (MenuItemKind.COMMAND, "timeline.range.move_to_row_above")
            )
        if row_idx is not None and row_idx < row_count - 1:
            move_items.append(
                (MenuItemKind.COMMAND, "timeline.range.move_to_row_below")
            )
        if move_items:
            items.append((MenuItemKind.SEPARATOR, None))
            items += move_items

        # Pre/post-end: show "Add" only when not yet set, "Delete" when set.
        # Pulled from the element rather than the selection so the menu still
        # makes sense when the right-clicked element isn't selected.
        pre_post_items = []
        if element.has_pre_start:
            pre_post_items.append(
                (MenuItemKind.COMMAND, "timeline.range.delete_pre_start")
            )
        else:
            pre_post_items.append(
                (MenuItemKind.COMMAND, "timeline.range.add_pre_start")
            )
        if element.has_post_end:
            pre_post_items.append(
                (MenuItemKind.COMMAND, "timeline.range.delete_post_end")
            )
        else:
            pre_post_items.append((MenuItemKind.COMMAND, "timeline.range.add_post_end"))
        items.append((MenuItemKind.SEPARATOR, None))
        items += pre_post_items

        items += [
            (MenuItemKind.SEPARATOR, None),
            (MenuItemKind.COMMAND, "timeline.component.copy"),
            (MenuItemKind.COMMAND, "timeline.component.paste"),
            (MenuItemKind.SEPARATOR, None),
            (MenuItemKind.COMMAND, "timeline.component.delete"),
        ]

        self.items = items
        super().__init__(element)
