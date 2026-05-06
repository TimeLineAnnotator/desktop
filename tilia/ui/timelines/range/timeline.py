from __future__ import annotations

import copy
import functools
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem

import tilia.errors
from tilia.log import logger
from tilia.requests import Get, Post, get, listen, post
from tilia.settings import settings
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.range.timeline import RangeTimeline
from tilia.ui import commands
from tilia.ui.coords import time_x_converter
from tilia.ui.dialogs.basic import ask_for_color
from tilia.ui.menus import RangeMenu
from tilia.ui.timelines.base.timeline import TimelineUI, with_elements
from tilia.ui.timelines.collection.collection import TimelineSelector, TimelineUIs
from tilia.ui.timelines.copy_paste import paste_into_element
from tilia.ui.timelines.harmony.level_label import LevelLabel
from tilia.ui.timelines.range.context_menu import RangeTimelineContextMenu
from tilia.ui.timelines.range.drag import MIN_DRAG_GAP
from tilia.ui.timelines.range.element import RangeUI
from tilia.ui.timelines.range.toolbar import RangeTimelineToolbar


def with_row(func: Callable) -> Callable:
    """Mirror of `with_elements` but for `selected_row`.

    If the wrapped callback receives no `row` argument (or `None`), fall
    back to `self.selected_row`. Return ``False`` when neither is
    available so the wrapped body always sees a concrete row.
    """

    @functools.wraps(func)
    def wrapper(
        self, row: RangeTimeline.Row | None = None, *args: Any, **kwargs: Any
    ) -> Any:
        if row is None:
            row = self.selected_row
        if row is None:
            return False
        return func(self, row, *args, **kwargs)

    return wrapper


class SelectedRowHighlight(QGraphicsRectItem):
    def __init__(self, height: float):
        super().__init__()
        self.set_height(height)
        self.set_fill("#20000000")
        self.set_pen_style_no_pen()
        self.setZValue(-100)
        self.setVisible(False)
        self.ignore_right_click = True

    def set_fill(self, color: str) -> None:
        self.setBrush(QColor(color))

    def set_pen_style_no_pen(self) -> None:
        self.setPen(QPen(Qt.PenStyle.NoPen))

    def set_height(self, height: float) -> None:
        self._height = height

    def update_position(self, y: float) -> None:
        self.setRect(
            get(Get.LEFT_MARGIN_X),
            y,
            get(Get.RIGHT_MARGIN_X) - get(Get.LEFT_MARGIN_X),
            self._height,
        )


class RangeTimelineUI(TimelineUI):
    TOOLBAR_CLASS = RangeTimelineToolbar
    ELEMENT_CLASS = RangeUI
    ACCEPTS_HORIZONTAL_ARROWS = True
    ACCEPTS_VERTICAL_ARROWS = True
    timeline_class = RangeTimeline
    menu_class = RangeMenu
    CONTEXT_MENU_CLASS = RangeTimelineContextMenu
    UPDATE_TRIGGERS = TimelineUI.UPDATE_TRIGGERS + [
        "rows",
        "default_row_height",
    ]
    DEFAULT_LABEL_PIXEL_SIZE = 12
    MIN_LABEL_PIXEL_SIZE = 6
    LABEL_VERTICAL_MARGIN = 2

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.selected_row: RangeTimeline.Row | None = (
            self.timeline.rows[0] if self.timeline.rows else None
        )
        self.row_labels: dict[str, LevelLabel] = {}
        self.row_highlight: SelectedRowHighlight | None = SelectedRowHighlight(
            self.default_row_height
        )
        self.scene.addItem(self.row_highlight)
        self.update_height()
        self.update_row_labels()

        listen(self, Post.SETTINGS_UPDATED, self.on_settings_updated)
        listen(self, Post.RANGE_TIMELINE_CREATED, self._delete_row_highlight)
        listen(self, Post.RANGE_TIMELINE_CLICKED, self._delete_row_highlight)

        post(Post.RANGE_TIMELINE_CREATED)
        # The post above runs every range timeline's `_delete_row_highlight`
        # listener — including this one's, since we just registered. That
        # collapses the "only one timeline shows the highlight" invariant
        # to "no timeline shows it"; recreate ours to make this timeline
        # the one that does.
        self._create_row_highlight()

    @property
    def default_range_size(self) -> float:
        return settings.get("range_timeline", "default_range_size")

    @property
    def rows(self) -> list[RangeTimeline.Row]:
        return self.timeline.rows

    def _create_row_highlight(self) -> None:
        self.row_highlight = SelectedRowHighlight(self.default_row_height)
        self.scene.addItem(self.row_highlight)
        self.update_highlight_position()

    def get_row_by_id(self, id_: str) -> RangeTimeline.Row | None:
        return self.timeline.get_row_by_id(id_)

    def get_row_by_index(self, index: int) -> RangeTimeline.Row | None:
        return self.timeline.get_row_by_index(index)

    def get_row_by_y(self, y: float) -> RangeTimeline.Row | None:
        if not self.rows:
            return None

        if y < 0:
            return None

        if y > self.height:
            return None

        # Walk through the rows in order; each row occupies
        # [row_y(idx), row_y(idx) + row_height_for(row)).
        running_y = 0.0
        for row in self.rows:
            row_h = self.row_height_for(row)
            if y < running_y + row_h:
                return row
            running_y += row_h
        return self.rows[-1]

    def row_index(self, row_id: str) -> int | None:
        return self.timeline.row_index(self.get_row_by_id(row_id))

    def get_data(self, attr: str) -> Any:
        if attr == "height":
            return self.height
        else:
            return super().get_data(attr)

    @property
    def default_row_height(self) -> int:
        return self.timeline.default_row_height or settings.get(
            "range_timeline", "default_row_height"
        )

    @property
    def label_alignment(self) -> str:
        return settings.get("range_timeline", "default_label_alignment")

    @property
    def height(self) -> int:
        bottom_margin = settings.get("range_timeline", "bottom_margin")
        return int(sum(self.row_height_for(r) for r in self.rows)) + bottom_margin

    @classmethod
    def register_commands(cls, collection: TimelineUIs) -> None:
        args = [
            ("add_row", "Add row", "", ""),
            ("add_row_above", "Add row above", "", "range-row-add-above"),
            ("add_row_below", "Add row below", "", "range-row-add-below"),
            ("remove_row", "Remove row", "", "range-row-remove"),
            ("rename_row", "Rename row", "", ""),
            ("set_row_color", "Set row color", "", ""),
            ("reset_row_color", "Reset row color", "", ""),
            ("reorder_row", "Reorder row", "", ""),
            ("add_range", "Add range", "r", "range-add"),
            ("join_ranges", "Join ranges", "j", "range-join"),
            ("separate_ranges", "Separate ranges", "", "range-separate"),
            ("merge_ranges", "Merge ranges", "e", "range-merge"),
            ("split_range", "Split range", "s", "range-split"),
            ("set_range_color", "Set color", "", ""),
            # move_to_row_above / move_to_row_below: shortcut field is empty
            # because Ctrl+Up / Ctrl+Down are dispatched via
            # Post.TIMELINE_KEY_PRESS_CTRL_UP/DOWN (see TimelineView and
            # TimelineUIs.on_ctrl_arrow_press) instead of being attached
            # to the QAction. Registering the same shortcut here as well
            # would produce a Qt "Ambiguous shortcut" warning.
            ("move_to_row_above", "Move to row above", "", ""),
            ("move_to_row_below", "Move to row below", "", ""),
            ("set_row_height", "Set default row height", "", ""),
            ("set_row_height_for_row", "Set height for this row", "", ""),
            ("reset_row_height_for_row", "Reset row height", "", ""),
            ("move_row_up", "Move row up", "", ""),
            ("move_row_down", "Move row down", "", ""),
            ("add_pre_start", "Add pre-start", "", ""),
            ("add_post_end", "Add post-end", "", ""),
            ("delete_pre_start", "Delete pre-start", "", ""),
            ("delete_post_end", "Delete post-end", "", ""),
            ("align_labels_left", "Align labels left", "", "FormatJustifyLeft"),
            ("align_labels_center", "Align labels center", "", "FormatJustifyCenter"),
            ("align_labels_right", "Align labels right", "", "FormatJustifyRight"),
            (
                "toggle_always_show_extensions",
                "Always show pre-start / post-end",
                "",
                "range-toggle-extensions",
            ),
            ("set_split_mode_all_rows", "Split mode: all rows", "", ""),
            ("set_split_mode_selected_row", "Split mode: selected row", "", ""),
        ]

        for name, text, shortcut, icon in args:
            cls.register_timeline_command(
                collection,
                name,
                getattr(cls, "on_" + name),
                TimelineSelector.FIRST,
                text=text,
                shortcut=shortcut,
                icon=icon,
            )

    def on_settings_updated(self, updated_settings: list[str]) -> None:
        if "range_timeline" in updated_settings:
            if self.row_highlight is not None:
                self.row_highlight.set_height(self.default_row_height)
                self.update_highlight_position()
            self.update_height()
            self.update_row_labels()
            for element in self:
                element.update_color()
                element.update_position()

    def update_highlight_position(self) -> None:
        if not self.row_highlight:
            return

        row_idx = (
            self.timeline.row_index(self.selected_row)
            if self.selected_row and self.selected_row in self.timeline.rows
            else 0
        )
        active_row = (
            self.timeline.rows[row_idx] if 0 <= row_idx < len(self.rows) else None
        )
        # Resize the highlight to match the active row's height (which may
        # differ from the timeline's default).
        self.row_highlight.set_height(self.row_height_for(active_row))
        y = self.row_y(row_idx)
        self.row_highlight.update_position(y)
        self.row_highlight.setVisible(True)

    def set_width(self, width: int) -> None:
        super().set_width(width)
        self.update_highlight_position()
        self.update_row_labels()

    def update_rows(self) -> None:
        # State restores (e.g. undo) replace the rows list with fresh Row
        # objects, so the cached `selected_row` reference can become stale.
        # Re-resolve by id so the selection survives the swap.
        if self.selected_row is not None:
            current = self.timeline.get_row_by_id(self.selected_row.id)
            self.selected_row = current
        if self.selected_row is None and self.rows:
            self.selected_row = self.rows[0]
        self.update_row_labels()
        self.update_highlight_position()
        self.update_height()
        # Row color or row height may have changed; ranges with no
        # per-component color inherit the row's color, and per-row height
        # changes shift downstream rows.
        for element in self:
            element.update_color()
            element.update_position()

    def update_default_row_height(self) -> None:
        if self.row_highlight is not None:
            self.row_highlight.set_height(self.default_row_height)
            self.update_highlight_position()
        for element in self:
            element.update_position()
        self.update_row_labels()
        self.update_height()

    def update_row_labels(self) -> None:
        current_row_ids = [row.id for row in self.timeline.rows]

        # Drop labels for rows that have been removed.
        for row_id in list(self.row_labels.keys()):
            if row_id not in current_row_ids:
                label = self.row_labels.pop(row_id)
                self.scene.removeItem(label)

        # Create labels for new rows; refresh text + font for all rows so
        # renames and per-row height changes are picked up.
        for row_idx, row in enumerate(self.timeline.rows):
            if row.id not in self.row_labels:
                label = LevelLabel(
                    get(Get.LEFT_MARGIN_X) - 2, self.row_y(row_idx) - 2, row.name
                )
                self.scene.addItem(label)
                self.row_labels[row.id] = label

            label = self.row_labels[row.id]
            label.setPlainText(row.name)
            self._apply_label_font(label, self.row_height_for(row))

        # Reposition every label after height/order changes shift the y of
        # rows below.
        for row_id, label in self.row_labels.items():
            label.set_position(
                get(Get.LEFT_MARGIN_X) - 2, self.row_y(self.row_index(row_id)) - 2
            )

    def _apply_label_font(self, label: LevelLabel, row_height: int) -> None:
        # Shrinks the row label so it fits when the user picks a small row
        # height. Without this clamp the default font size overflows into
        # the next row and gets clipped.
        target = max(
            self.MIN_LABEL_PIXEL_SIZE,
            min(
                self.DEFAULT_LABEL_PIXEL_SIZE,
                row_height - self.LABEL_VERTICAL_MARGIN,
            ),
        )
        font = QFont(label.font())
        font.setPixelSize(target)
        label.setFont(font)

    def on_add_row(
        self,
        idx: int | None = None,
        name: str | None = None,
        color: str | None = None,
    ) -> bool:
        self.timeline.add_row(name=name, color=color, idx=idx)
        self.update_height()
        return True

    def on_add_row_above(self) -> bool:
        ref_row = self.selected_row
        idx = self.timeline.row_index(ref_row) if ref_row is not None else 0
        if idx is None:
            idx = 0
        return self.on_add_row(idx=idx)

    def on_add_row_below(self) -> bool:
        ref_row = self.selected_row
        idx = (
            self.timeline.row_index(ref_row) + 1
            if ref_row is not None
            else self.timeline.row_count
        )
        return self.on_add_row(idx=idx)

    @with_row
    def on_remove_row(self, row: RangeTimeline.Row) -> bool:
        if self.timeline.row_count <= 1:
            return False

        success = self.timeline.remove_row(row)
        if success and self.selected_row == row:
            self.selected_row = self.timeline.rows[0] if self.timeline.rows else None

        self.update_height()
        self.update_row_labels()
        return success

    @with_elements
    def on_copy_element(self, elements: list[RangeUI]) -> bool:
        # v2 will support cross-row paste; for now, restrict copy to a
        # single row so paste keeps the row context unambiguous.
        if len({e.get_data("row_id") for e in elements}) > 1:
            tilia.errors.display(
                tilia.errors.COMPONENTS_COPY_ERROR,
                "Cannot copy ranges from multiple rows at once.",
            )
            return False

        return super().on_copy_element(elements)

    def paste_single_into_selected_elements(
        self, paste_data: list[dict] | dict
    ) -> None:
        for element in self.element_manager.get_selected_elements():
            self.deselect_element(element)
            paste_into_element(element, paste_data[0])
            self.select_element(element)

    def paste_multiple_into_selected_elements(
        self, paste_data: list[dict] | dict
    ) -> None:
        paste_data = sorted(paste_data, key=lambda md: md["context"]["start"])

        first = self.selected_elements[0]
        self.deselect_element(first)
        paste_into_element(first, paste_data[0])
        self.select_element(first)

        self._create_pasted_ranges(
            paste_data[1:],
            paste_data[0]["context"]["start"],
            first.get_data("start"),
            first.get_data("row_id"),
        )

    def paste_single_into_timeline(self, paste_data: list[dict] | dict) -> None:
        return self.paste_multiple_into_timeline(paste_data)

    def paste_multiple_into_timeline(self, paste_data: list[dict] | dict) -> None:
        target_row = self.selected_row or (self.rows[0] if self.rows else None)
        if target_row is None:
            return
        reference_time = min(md["context"]["start"] for md in paste_data)
        self._create_pasted_ranges(
            paste_data,
            reference_time,
            get(Get.SELECTED_TIME),
            target_row.id,
        )

    def _create_pasted_ranges(
        self,
        paste_data: list[dict],
        reference_time: float,
        target_time: float,
        row_id: str,
    ) -> None:
        old_to_new: dict = {}
        old_joined_right_pairs: list[tuple] = []
        for d in copy.deepcopy(paste_data):
            start = d["context"].pop("start")
            end = d["context"].pop("end")
            old_id = d["context"].pop("id", None)
            old_joined_right = d["context"].pop("joined_right", None)
            duration = end - start
            new_start = target_time + (start - reference_time)
            comp, _ = self.timeline.create_component(
                kind=ComponentKind.RANGE,
                start=new_start,
                end=new_start + duration,
                row_id=row_id,
                **d["values"],
                **d["context"],
            )
            if comp is None:
                continue
            if old_id is not None:
                old_to_new[old_id] = comp.id
            old_joined_right_pairs.append((comp.id, old_joined_right))

        # Restore joins where both endpoints survived the paste batch.
        for new_id, old_partner_id in old_joined_right_pairs:
            new_partner_id = old_to_new.get(old_partner_id)
            if new_partner_id is not None:
                self.timeline.set_component_data(new_id, "joined_right", new_partner_id)

    @with_row
    def on_add_range(
        self,
        row: RangeTimeline.Row,
        start: float | None = None,
        end: float | None = None,
    ) -> bool:
        if start is None:
            start = get(Get.SELECTED_TIME)

        media_duration = get(Get.MEDIA_DURATION)

        if start >= media_duration:
            return False

        if end is None:
            end = start + self.default_range_size

        if end > media_duration:
            end = media_duration

        component, _ = self.timeline.create_component(
            kind=ComponentKind.RANGE, start=start, end=end, row_id=row.id
        )

        return component is not None

    @with_elements
    def on_join_ranges(self, elements: list[RangeUI]) -> bool:
        success, reason = self.timeline.component_manager.join(
            self.elements_to_components(elements)
        )
        if not success:
            post(Post.DISPLAY_ERROR, "Error joining ranges", reason)
        return success

    @with_elements
    def on_merge_ranges(self, elements: list[RangeUI]) -> bool:
        success, reason = self.timeline.component_manager.merge(
            self.elements_to_components(elements)
        )
        if not success:
            post(Post.DISPLAY_ERROR, "Error merging ranges", reason)
        return success

    def on_split_range(
        self, time: float | None = None, row: RangeTimeline.Row | None = None
    ) -> bool:
        if time is None:
            time = get(Get.SELECTED_TIME)

        # When the user passes an explicit row (e.g. via context menu) we
        # always honour it. Otherwise consult the toggle: if "split all rows"
        # is on, slice through every row at `time`; if off, fall back to the
        # selected row.
        if row is None and settings.get("range_timeline", "split_all_rows"):
            target_rows = list(self.timeline.rows)
        else:
            if row is None:
                row = self.selected_row
            if row is None:
                return False
            target_rows = [row]

        any_success = False
        # Capture join boundaries that the split is about to separate so we
        # can nudge the two halves apart afterwards (matches the gap that
        # the explicit Separate ranges command introduces). Doing this
        # per-row before the split keeps the logic at the UI layer where
        # `time_x_converter` and `MIN_DRAG_GAP` already live.
        boundary_pairs: list[tuple[Any, Any]] = []
        for target_row in target_rows:
            for r in self.timeline:
                if r.row_id != target_row.id or r.joined_right is None:
                    continue
                partner = self.timeline.get_component(r.joined_right)
                if partner is not None and partner.start == time:
                    boundary_pairs.append((r, partner))

        for target_row in target_rows:
            success, reason = self.timeline.component_manager.split(time, target_row.id)
            if success:
                any_success = True
            elif reason and reason != "Nothing to split at this time.":
                # Silently ignore the "nothing to split" case — the user may
                # press the shortcut at any time, so don't spam errors for it.
                post(Post.DISPLAY_ERROR, "Error splitting range", reason)

        if boundary_pairs:
            half_gap_time = time_x_converter.get_time_by_x(
                MIN_DRAG_GAP / 2
            ) - time_x_converter.get_time_by_x(0)
            for left, right in boundary_pairs:
                self.timeline.set_component_data(
                    left.id, "end", left.end - half_gap_time
                )
                self.timeline.set_component_data(
                    right.id, "start", right.start + half_gap_time
                )

        return any_success

    @with_elements
    def on_separate_ranges(self, elements: list[RangeUI]) -> bool:
        selected = self.elements_to_components(elements)
        selected_ids = {c.id for c in selected}

        # Capture pairs whose join link will be cleared so we can nudge their
        # extremities apart afterwards. A link is cleared when either side is
        # in the selection (see RangeTLComponentManager.separate).
        pairs_to_nudge = []
        for c in self.timeline:
            if c.joined_right is None:
                continue
            if c.id in selected_ids or c.joined_right in selected_ids:
                partner = self.timeline.get_component(c.joined_right)
                if partner is not None:
                    pairs_to_nudge.append((c, partner))

        success, reason = self.timeline.component_manager.separate(selected)
        if not success:
            post(Post.DISPLAY_ERROR, "Error separating ranges", reason)
            return success

        # Nudge each side by half the proximity gap so the formerly-shared
        # edge ends up centered between the two ranges, with `MIN_DRAG_GAP`
        # pixels of space between them.
        half_gap_time = time_x_converter.get_time_by_x(
            MIN_DRAG_GAP / 2
        ) - time_x_converter.get_time_by_x(0)
        for left, right in pairs_to_nudge:
            self.timeline.set_component_data(left.id, "end", left.end - half_gap_time)
            self.timeline.set_component_data(
                right.id, "start", right.start + half_gap_time
            )

        return success

    @with_elements
    def on_move_to_row_above(self, elements: list[RangeUI]) -> bool:
        return self._move_to_row(elements, -1)

    @with_elements
    def on_move_to_row_below(self, elements: list[RangeUI]) -> bool:
        return self._move_to_row(elements, +1)

    def _move_to_row(self, elements: list[RangeUI], delta: int) -> bool:
        # A join is a same-row invariant. Moving any range in a chain has to
        # carry every other range in that chain, or the join would straddle
        # rows.
        chain_ids: set = set()
        for e in elements:
            chain_ids.update(self._joined_chain_ids(e.id))
        expanded = [self.id_to_element[cid] for cid in chain_ids]

        for e in expanded:
            current_idx = self.row_index(e.get_data("row_id"))
            if current_idx is None:
                return False
            target_idx = current_idx + delta
            if not 0 <= target_idx < self.timeline.row_count:
                return False
        for e in expanded:
            current_idx = self.row_index(e.get_data("row_id"))
            target_idx = current_idx + delta
            target_row_id = self.timeline.rows[target_idx].id
            self.timeline.set_component_data(e.id, "row_id", target_row_id)
        return True

    def _joined_chain_ids(self, range_id) -> set:
        """Return the ids of all ranges in the join chain containing range_id."""
        seen: set = set()
        stack = [range_id]
        while stack:
            cid = stack.pop()
            if cid in seen:
                continue
            seen.add(cid)
            comp = self.timeline.get_component(cid)
            if comp is None:
                continue
            if comp.joined_right is not None and comp.joined_right not in seen:
                stack.append(comp.joined_right)
            for other in self.timeline:
                if other.joined_right == cid and other.id not in seen:
                    stack.append(other.id)
        return seen

    @with_row
    def on_rename_row(
        self, row: RangeTimeline.Row, new_name: str | None = None
    ) -> bool:
        if not new_name:
            success, new_name = get(
                Get.FROM_USER_STRING,
                "Rename row",
                "Insert new row name",
                text=row.name,
            )
            if not success:
                return False

        self.timeline.rename_row(row, new_name)
        return True

    def on_set_row_height(self, height: int | None = None) -> bool:
        if height is None:
            success, height = get(
                Get.FROM_USER_INT,
                "Set default row height",
                "Insert new default row height",
                value=self.default_row_height,
                minValue=10,
            )
            if not success:
                return False
        # Route through the collection (rather than `self.timeline.set_data`)
        # so `Post.TIMELINE_SET_DATA_DONE` is posted on success — that's
        # what triggers the UI refresh when the default row height changes.
        return get(Get.TIMELINE_COLLECTION).set_timeline_data(
            self.id, "default_row_height", height
        )

    @with_row
    def on_set_row_height_for_row(
        self,
        row: RangeTimeline.Row,
        height: int | None = None,
    ) -> bool:
        current = self.row_height_for(row)
        if height is None:
            success, height = get(
                Get.FROM_USER_INT,
                "Set row height",
                f"Height for row '{row.name}'",
                value=current,
                minValue=10,
            )
            if not success:
                return False
        if row.height == height:
            return False
        self.timeline.set_row_height(row, height)
        self.update_height()
        return True

    @with_row
    def on_reset_row_height_for_row(self, row: RangeTimeline.Row) -> bool:
        if row.height is None:
            return False
        self.timeline.set_row_height(row, None)
        self.update_height()
        return True

    @with_row
    def on_set_row_color(self, row: RangeTimeline.Row, color: str | None) -> bool:
        if color:
            self.timeline.set_row_color(row, color)
            return True

        ok, new_color = ask_for_color(row.color)
        if ok and new_color.isValid():
            self.timeline.set_row_color(row, new_color.name())
            return True
        return False

    @with_row
    def on_reset_row_color(self, row: RangeTimeline.Row) -> bool:
        if row.color is None:
            return False
        self.timeline.reset_row_color(row)
        return True

    def on_reorder_row(
        self,
        row: RangeTimeline.Row | None = None,
        new_index: int | None = None,
    ) -> bool:
        # Not @with_row: reordering needs an explicit target row, no
        # selected-row fallback.
        if row is None or new_index is None:
            return False
        return self.timeline.reorder_row(row, new_index)

    @with_row
    def on_move_row_up(self, row: RangeTimeline.Row) -> bool:
        idx = self.timeline.row_index(row)
        if idx is None or idx == 0:
            return False
        return self.timeline.reorder_row(row, idx - 1)

    @with_row
    def on_move_row_down(self, row: RangeTimeline.Row) -> bool:
        idx = self.timeline.row_index(row)
        if idx is None or idx >= self.timeline.row_count - 1:
            return False
        return self.timeline.reorder_row(row, idx + 1)

    def on_set_range_color(
        self, ranges: list[RangeUI] | None, color: str | None
    ) -> bool:
        if not ranges:
            ranges = self.selected_components
            if not ranges:
                return False

        if not color:
            ok, new_color = ask_for_color(ranges[0].get_data("color"))
            if ok and new_color.isValid():
                for r in ranges:
                    self.timeline.set_component_data(r.id, "color", new_color.name())
                return True
        return False

    @with_elements
    def on_add_pre_start(
        self, elements: list[RangeUI], length: float | None = None
    ) -> bool:
        if length is None:
            accept, length = get(
                Get.FROM_USER_FLOAT, "Add pre-start", "Pre-start length"
            )
            if not accept:
                return False
        if length <= 0:
            return False
        for e in elements:
            new_pre_start = max(0.0, e.get_data("start") - length)
            self.timeline.set_component_data(e.id, "pre_start", new_pre_start)
        return True

    @with_elements
    def on_add_post_end(
        self, elements: list[RangeUI], length: float | None = None
    ) -> bool:
        if length is None:
            accept, length = get(Get.FROM_USER_FLOAT, "Add post-end", "Post-end length")
            if not accept:
                return False
        if length <= 0:
            return False
        media_duration = get(Get.MEDIA_DURATION)
        for e in elements:
            new_post_end = min(media_duration, e.get_data("end") + length)
            self.timeline.set_component_data(e.id, "post_end", new_post_end)
        return True

    @with_elements
    def on_delete_pre_start(self, elements: list[RangeUI]) -> bool:
        changed = False
        for e in elements:
            if e.get_data("pre_start") != e.get_data("start"):
                self.timeline.set_component_data(e.id, "pre_start", e.get_data("start"))
                changed = True
        return changed

    def _set_label_alignment(self, alignment: str) -> bool:
        if settings.get("range_timeline", "default_label_alignment") == alignment:
            return False
        settings.set("range_timeline", "default_label_alignment", alignment)
        post(Post.SETTINGS_UPDATED, ["range_timeline"])
        return True

    def on_align_labels_left(self) -> bool:
        return self._set_label_alignment("left")

    def on_align_labels_center(self) -> bool:
        return self._set_label_alignment("center")

    def on_align_labels_right(self) -> bool:
        return self._set_label_alignment("right")

    def on_toggle_always_show_extensions(self) -> bool:
        current = settings.get("range_timeline", "always_show_extensions")
        settings.set("range_timeline", "always_show_extensions", not current)
        post(Post.SETTINGS_UPDATED, ["range_timeline"])
        return True

    def on_set_split_mode_all_rows(self) -> bool:
        return self._set_split_mode(True)

    def on_set_split_mode_selected_row(self) -> bool:
        return self._set_split_mode(False)

    @staticmethod
    def _set_split_mode(all_rows: bool) -> bool:
        if bool(settings.get("range_timeline", "split_all_rows")) == all_rows:
            return False
        settings.set("range_timeline", "split_all_rows", all_rows)
        post(Post.SETTINGS_UPDATED, ["range_timeline"])
        return True

    @with_elements
    def on_delete_post_end(self, elements: list[RangeUI]) -> bool:
        changed = False
        for e in elements:
            if e.get_data("post_end") != e.get_data("end"):
                self.timeline.set_component_data(e.id, "post_end", e.get_data("end"))
                changed = True
        return changed

    def row_y(self, row_index: int) -> float:
        # Cumulative top-y of the row at `row_index`. Each row may set
        # its own `height`; rows without one inherit the timeline's
        # default row height.
        if row_index <= 0:
            return 0.0
        total = 0.0
        for row in self.rows[:row_index]:
            total += self.row_height_for(row)
        return total

    def row_height_for(self, row: RangeTimeline.Row | None) -> int:
        if row is None or row.height is None:
            return self.default_row_height
        return row.height

    def update_height(self) -> None:
        super().update_height()
        self.update_highlight_position()

    def on_horizontal_arrow_press(self, arrow: str) -> None:
        if not self.has_selected_elements:
            return
        if arrow not in ("right", "left"):
            logger.error("RangeTimelineUI: invalid horizontal arrow %r.", arrow)
            return

        if arrow == "right":
            self._deselect_all_but_last()
        else:
            self._deselect_all_but_first()

        selected = self.element_manager.get_selected_elements()[0]
        same_row = sorted(
            e for e in self if e.get_data("row_id") == selected.get_data("row_id")
        )
        idx = same_row.index(selected)
        if arrow == "right":
            if idx >= len(same_row) - 1:
                return
            target = same_row[idx + 1]
        else:
            if idx == 0:
                return
            target = same_row[idx - 1]

        self.deselect_element(selected)
        self.select_element(target)

    def on_vertical_arrow_press(self, arrow: str) -> None:
        if arrow not in ("up", "down"):
            logger.error("RangeTimelineUI: invalid vertical arrow %r.", arrow)
            return
        self._handle_arrow_navigation(arrow)

    def on_ctrl_vertical_arrow_press(self, direction: str) -> None:
        cmd = (
            "timeline.range.move_to_row_above"
            if direction == "up"
            else "timeline.range.move_to_row_below"
        )
        commands.execute(cmd)

    def _handle_arrow_navigation(self, arrow: str) -> None:
        selection = self.selected_components
        if not selection:
            return

        reference_range = selection[-1]
        current_row = self.timeline.get_row_by_id(reference_range.row_id)
        current_row_idx = self.timeline.row_index(current_row)
        if current_row_idx is None:
            return

        step = -1 if arrow == "up" else 1
        target_row_idx = current_row_idx + step
        candidates: list = []
        while 0 <= target_row_idx < self.timeline.row_count:
            target_row_id = self.timeline.rows[target_row_idx].id
            candidates = self.timeline.get_ranges_by_row(target_row_id)
            if candidates:
                break
            target_row_idx += step

        if not candidates:
            return

        overlapping = [
            c
            for c in candidates
            if c.start < reference_range.end and c.end > reference_range.start
        ]

        if overlapping:
            ref_center = (reference_range.start + reference_range.end) / 2
            target_range = min(
                overlapping, key=lambda c: abs((c.start + c.end) / 2 - ref_center)
            )
        else:
            target_range = min(
                candidates, key=lambda c: abs(c.start - reference_range.start)
            )

        target_ui = self.get_component_ui(target_range)
        if target_ui:
            for element in list(self.selected_elements):
                self.deselect_element(element)
            self.select_element(target_ui)
            self.selected_row = self.timeline.rows[target_row_idx]
            self.update_highlight_position()

    def _delete_row_highlight(self, *_) -> None:
        if self.row_highlight is None:
            return
        self.scene.removeItem(self.row_highlight)
        self.row_highlight = None

    def on_left_click(
        self,
        item: QGraphicsItem,
        modifier: Qt.KeyboardModifier,
        double: bool,
        x: int,
        y: int,
    ) -> None:
        post(Post.RANGE_TIMELINE_CLICKED)
        super().on_left_click(item, modifier, double, x, y)

        if not self.row_highlight:
            self._create_row_highlight()
        row = self.get_row_by_y(y)
        if row is not None:
            self.selected_row = row
            self.update_highlight_position()
