from __future__ import annotations

from typing import TYPE_CHECKING

from tilia.timelines.base.component import SegmentLikeTimelineComponent
from tilia.timelines.base.validators import (
    validate_color,
    validate_read_only,
    validate_string,
    validate_time,
)
from tilia.timelines.component_kinds import ComponentKind

if TYPE_CHECKING:
    from tilia.timelines.range.timeline import RangeTimeline


class Range(SegmentLikeTimelineComponent):
    SERIALIZABLE = [
        "start",
        "end",
        "row_id",
        "label",
        "color",
        "comments",
        "joined_right",
        "pre_start",
        "post_end",
    ]

    validators = {
        "timeline": validate_read_only,
        "id": validate_read_only,
        "start": validate_time,
        "end": validate_time,
        "pre_start": validate_time,
        "post_end": validate_time,
        "label": validate_string,
        "color": lambda x: True if x is None else validate_color(x),
        "comments": validate_string,
        "row_id": validate_string,
        "joined_right": lambda x: x is None or isinstance(x, (int, str)),
    }

    KIND = ComponentKind.RANGE
    ORDERING_ATTRS = ("start", "row_id")

    def __init__(
        self,
        timeline: RangeTimeline,
        id: int,
        start: float,
        end: float,
        row_id: str,
        label: str = "",
        color: str | None = None,
        comments: str = "",
        joined_right: str | None = None,
        pre_start: float | None = None,
        post_end: float | None = None,
        **_,
    ):
        self._start = start
        self._end = end
        self.row_id = row_id
        self.label = label
        self.color = color
        self.comments = comments
        self.joined_right = joined_right
        # Default to start/end (no extension visible). Mirror hierarchy.
        self.pre_start = pre_start if pre_start is not None else start
        self.post_end = post_end if post_end is not None else end

        super().__init__(timeline, id)

    @property
    def start(self) -> float:
        return self._start

    @start.setter
    def start(self, value: float) -> None:
        prev_start = self._start
        self._start = value
        # If the user's edit pushes start past pre_start, drag pre_start
        # along. If pre_start was at the previous start (i.e. no extension
        # set), keep it pinned to start.
        if self.pre_start > value or self.pre_start == prev_start:
            self.pre_start = value

    @property
    def end(self) -> float:
        return self._end

    @end.setter
    def end(self, value: float) -> None:
        prev_end = self._end
        self._end = value
        # Mirror of the start setter: drag post_end along when end moves
        # past it, or keep it pinned to end if no extension was set
        # (post_end was at prev_end).
        if self.post_end < value or self.post_end == prev_end:
            self.post_end = value

    def __repr__(self):
        return f"Range({self.start}, {self.end}, {self.row_id}, {self.label})"
