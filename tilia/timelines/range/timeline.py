from __future__ import annotations

import functools
import random
import string
from typing import Any

from tilia.requests import Get, Post, get, post
from tilia.settings import settings
from tilia.timelines.base.component.segmentlike import (
    crop_segmentlike,
    scale_segmentlike,
)
from tilia.timelines.base.timeline import (
    Timeline,
    TimelineComponentManager,
    TimelineFlag,
)
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.range.components import Range


def generate_row_id() -> str:
    return "".join(random.choices(string.ascii_letters + string.digits, k=6))


class RangeTLComponentManager(TimelineComponentManager):
    def __init__(self, timeline: RangeTimeline):
        super().__init__(timeline, [ComponentKind.RANGE])
        self.scale = functools.partial(scale_segmentlike, self)
        self.crop = functools.partial(crop_segmentlike, self)
        self._restoring_state = False

    def restore_state(self, prev_state: dict) -> None:
        # restore_state diffs current vs snapshot by component hash, then
        # deletes and recreates any range whose hash changed (e.g. a
        # post_end edit) to match the snapshot. Suppress delete_component's
        # joined_right cascade during that: otherwise it clears the join
        # on an unrelated neighbor whose own hash didn't change — and
        # because its hash didn't change, it isn't re-deserialized either,
        # so the cleared join is never restored.
        self._restoring_state = True
        try:
            super().restore_state(prev_state)
        finally:
            self._restoring_state = False

    def _validate_component_creation(
        self, kind: ComponentKind, **kwargs: Any
    ) -> tuple[bool, str]:
        if kind != ComponentKind.RANGE:
            return False, f"Invalid component kind: {kind}"

        start = kwargs.get("start")
        end = kwargs.get("end")
        row_id = kwargs.get("row_id")

        if not row_id or row_id not in self.timeline.row_ids:
            return False, "Invalid row ID."

        if start >= end:
            return False, "Start time must be before end time."

        media_duration = get(Get.MEDIA_DURATION)
        if start < 0 or end > media_duration:
            return False, "Range is outside media bounds."

        pre_start = kwargs.get("pre_start")
        if pre_start is not None and pre_start < 0:
            return False, "pre_start is outside media bounds."

        post_end = kwargs.get("post_end")
        if post_end is not None and post_end > media_duration:
            return False, "post_end is outside media bounds."

        return True, ""

    def join(self, ranges: list[Range]) -> tuple[bool, str]:
        if len(ranges) < 2:
            return False, "Select at least two ranges."

        row_id = ranges[0].row_id
        if any(r.row_id != row_id for r in ranges):
            return False, "Ranges must be in the same row."

        ranges = sorted(ranges)

        for i in range(len(ranges) - 1):
            if ranges[i].end > ranges[i + 1].start:
                return False, "Cannot join overlapping ranges."

        for i in range(len(ranges) - 1):
            if ranges[i].end != ranges[i + 1].start:
                self.timeline.set_component_data(
                    ranges[i].id, "end", ranges[i + 1].start
                )
            self.timeline.set_component_data(
                ranges[i].id, "joined_right", ranges[i + 1].id
            )

        return True, ""

    def separate(self, ranges: list[Range]) -> tuple[bool, str]:
        if not ranges:
            return False, "No ranges selected."

        selected_ids = {r.id for r in ranges}
        for r in ranges:
            if r.joined_right is not None:
                self.timeline.set_component_data(r.id, "joined_right", None)
        for c in list(self):
            if c.joined_right in selected_ids:
                self.timeline.set_component_data(c.id, "joined_right", None)
        return True, ""

    def merge(self, ranges: list[Range]) -> tuple[bool, str]:
        """Merge ≥2 same-row ranges into a single range spanning from the
        first range's start to the last range's end. Non-empty label and
        comments are joined by `merge_separator`. Pre-start is taken from
        the first range; post-end from the last. Joins on the merged-away
        ranges are dropped; joins crossing into the merger are rewired to
        the surviving range."""
        if len(ranges) < 2:
            return False, "Select at least two ranges."

        row_id = ranges[0].row_id
        if any(r.row_id != row_id for r in ranges):
            return False, "Ranges must be in the same row."

        ranges = sorted(ranges)
        merged_ids = {r.id for r in ranges}
        survivor = ranges[0]
        last = ranges[-1]
        new_end = last.end
        new_pre_start = survivor.pre_start
        new_post_end = last.post_end

        separator = self.timeline.merge_separator
        attr_to_new_value: dict[str, str | None] = {}
        for attr in ("label", "comments"):
            values = [r.get_data(attr) for r in ranges]
            non_empty = [v for v in values if v]
            if not non_empty:
                new_value = ""
            elif len(set(non_empty)) == 1:
                new_value = non_empty[0]
            else:
                new_value = separator.join(non_empty)
            if new_value != survivor.get_data(attr):
                attr_to_new_value[attr] = new_value

        # Rewire any external join pointing into a merged-away range to
        # point at the survivor instead. Skip rewiring joins between
        # merged-away ranges (they're going to be deleted).
        for c in list(self):
            if c.id in merged_ids:
                continue
            if c.joined_right in merged_ids:
                self.timeline.set_component_data(c.id, "joined_right", survivor.id)

        # Drop the survivor's own outgoing join (it would point at one of
        # the now-deleted ranges). If the original chain extended past
        # the merge, that link will be re-set by the rewire above.
        self.timeline.set_component_data(survivor.id, "joined_right", None)

        # Stretch the survivor to span the full merged region.
        self.timeline.set_component_data(survivor.id, "end", new_end)
        self.timeline.set_component_data(survivor.id, "pre_start", new_pre_start)
        self.timeline.set_component_data(survivor.id, "post_end", new_post_end)
        for attr, value in attr_to_new_value.items():
            self.timeline.set_component_data(survivor.id, attr, value)

        # Delete every range besides the survivor.
        to_delete = [r for r in ranges if r.id != survivor.id]
        if to_delete:
            self.timeline.delete_components(to_delete)

        return True, ""

    def split(self, time: float, row_id: str) -> tuple[bool, str]:
        """Split at `time` on the given row.

        Mid-range (start < time < end): split into two joined ranges.
        Exactly on a join boundary (time == start of a range with an
        incoming join): separate that join.
        Otherwise: no-op.
        """
        if not row_id or row_id not in self.timeline.row_ids:
            return False, "No row to split in."

        same_row = self.timeline.get_ranges_by_row(row_id)

        # Mid-range split: time strictly inside a range. The original range
        # becomes the left half (its `end` shrinks); a new range becomes
        # the right half. Joins are wired so the split is invisible
        # outside this row.
        for r in same_row:
            if r.start < time < r.end:
                old_end = r.end
                old_post_end = r.post_end
                old_joined_right = r.joined_right

                new_component, _ = self.timeline.create_component(
                    ComponentKind.RANGE,
                    start=time,
                    end=old_end,
                    row_id=row_id,
                    label=r.label,
                    color=r.color,
                    comments=r.comments,
                    joined_right=old_joined_right,
                    pre_start=time,
                    post_end=old_post_end,
                )
                if new_component is None:
                    return False, "Could not create new range."

                # Shrinking end auto-collapses the original's post_end (the
                # right half carries the original post_end now).
                self.timeline.set_component_data(r.id, "end", time)
                self.timeline.set_component_data(r.id, "joined_right", new_component.id)
                return True, ""

        # Boundary separation: time falls exactly on a join boundary.
        for r in same_row:
            if r.start == time:
                for other in same_row:
                    if other.joined_right == r.id:
                        self.timeline.set_component_data(other.id, "joined_right", None)
                        return True, ""
                break

        return False, "Nothing to split at this time."

    def delete_component(self, component: Range) -> None:
        # Break any incoming join links pointing at this range. The deleted
        # range's own `joined_right` (if any) is dropped with the component.
        # Skip the cascade during state restore: the restored snapshot
        # already encodes whatever join state should hold afterwards.
        if not self._restoring_state:
            for c in list(self):
                if c.id != component.id and c.joined_right == component.id:
                    self.timeline.set_component_data(c.id, "joined_right", None)
        super().delete_component(component)


def _validate_default_row_height(value: Any) -> bool:
    return value is None or (isinstance(value, int) and value >= 10)


class RangeTimeline(Timeline):
    COMPONENT_MANAGER_CLASS = RangeTLComponentManager
    FLAGS = Timeline.FLAGS + [
        TimelineFlag.COMPONENTS_COLORED,
        TimelineFlag.COMPONENTS_COPYABLE,
        TimelineFlag.COMPONENTS_IMPORTABLE,
    ]

    SERIALIZABLE = Timeline.SERIALIZABLE + [
        "rows",
        "default_row_height",
    ]

    validators = Timeline.validators.copy()
    validators["rows"] = lambda x: (isinstance(x, list), "")
    validators["default_row_height"] = _validate_default_row_height

    class Row:
        def __init__(
            self,
            id: str,
            name: str,
            color: str | None = None,
            height: int | None = None,
        ):
            self.id = id
            self.name = name
            self.color = color
            self.height = height

        def __eq__(self, other: object) -> bool:
            if not isinstance(other, RangeTimeline.Row):
                return False
            return (
                self.id == other.id
                and self.name == other.name
                and self.color == other.color
                and self.height == other.height
            )

        def __repr__(self) -> str:
            return (
                f"Row(id={self.id}, name='{self.name}', "
                f"color='{self.color}', height={self.height})"
            )

        def to_dict(self) -> dict[str, Any]:
            return {
                "id": self.id,
                "name": self.name,
                "color": self.color,
                "height": self.height,
            }

        @classmethod
        def from_dict(cls, dict_: dict) -> RangeTimeline.Row | None:
            try:
                return cls(
                    id=dict_["id"],
                    name=dict_["name"],
                    color=dict_["color"],
                    height=dict_.get("height"),
                )
            except AttributeError:
                return None

    def __init__(
        self,
        *args,
        rows: list[dict] | None = None,
        default_row_height: int | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        if rows is None:
            rows = []
        _rows: list[RangeTimeline.Row] = []

        for row in rows:
            assert isinstance(row, dict), "Row must be a dictionary."
            _rows.append(RangeTimeline.Row.from_dict(row))

        self.rows = _rows
        self.default_row_height = default_row_height

    @property
    def default_color(self) -> str:
        return settings.get("range_timeline", "default_range_color")

    @property
    def merge_separator(self) -> str:
        return settings.get("range_timeline", "merge_separator")

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def row_ids(self) -> list[str]:
        return [r.id for r in self.rows]

    def row_index(self, row: Row) -> int | None:
        if row not in self.rows:
            return None
        else:
            return self.rows.index(row)

    def get_row_initial_name(self) -> str:
        return f"Row {len(self.rows)}"

    def get_row_by_id(self, id_: str) -> Row | None:
        for row in self.rows:
            if row.id == id_:
                return row
        return None

    def get_row_by_index(self, index: int) -> Row | None:
        if index < 0 or index >= len(self.rows):
            return None
        return self.rows[index]

    def get_ranges_by_row(self, row_id: str) -> list[Range]:
        """Return ranges on the given row, ordered by start time."""
        return sorted(r for r in self if r.row_id == row_id)

    def setup_blank_timeline(self) -> None:
        if not self.rows:
            self.add_row(self.get_row_initial_name())

    def _post_rows_update(self) -> None:
        post(Post.TIMELINE_SET_DATA_DONE, self.id, "rows", self.rows)

    def add_row(
        self,
        name: str | None = None,
        color: str | None = None,
        idx: int | None = None,
        height: int | None = None,
    ) -> RangeTimeline.Row:
        new_id = generate_row_id()
        while new_id in self.row_ids:
            new_id = generate_row_id()
        if name is None:
            name = self.get_row_initial_name()
        row = self.Row(new_id, name, color, height)
        if idx is None:
            idx = len(self.rows)
        self.rows.insert(idx, row)
        self._post_rows_update()

        return row

    def remove_row(self, row: Row) -> bool:
        if row not in self.rows:
            return False

        to_delete = self.get_ranges_by_row(row.id)
        if to_delete:
            self.delete_components(to_delete)

        self.rows.remove(row)
        self._post_rows_update()
        return True

    def clear_rows(self) -> None:
        # Caller is responsible for restoring the >=1-row invariant (typically
        # via setup_blank_timeline) once any row-creation pass has completed.
        self.rows = []
        self._post_rows_update()

    def rename_row(self, row: Row, new_name: str) -> None:
        row.name = new_name
        self._post_rows_update()

    def reorder_row(self, row: Row, new_index: int) -> bool:
        if row not in self.rows:
            return False
        new_index = max(0, min(new_index, len(self.rows) - 1))
        self.rows.remove(row)
        self.rows.insert(new_index, row)
        self._post_rows_update()
        return True

    def set_row_color(self, row: Row, color: str) -> None:
        row.color = color
        self._post_rows_update()

    def set_row_height(self, row: Row, height: int | None) -> None:
        # height=None means "fall back to the timeline's default_row_height".
        row.height = height
        self._post_rows_update()

    def reset_row_color(self, row: Row) -> None:
        row.color = None
        self._post_rows_update()

    def set_data(self, attr: str, value: Any) -> tuple[Any, bool]:
        if attr == "rows":
            value = [
                RangeTimeline.Row.from_dict(r) if isinstance(r, dict) else r
                for r in value
            ]
        return super().set_data(attr, value)

    def _get_base_state(self) -> dict:
        state = super()._get_base_state()
        state["rows"] = [r.to_dict() for r in self.rows]
        return state
