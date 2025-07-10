from __future__ import annotations

import functools
from typing import Any

from tilia.requests import post, Post
from tilia.timelines.base.component import (
    PointLikeTimelineComponent,
    SegmentLikeTimelineComponent,
)
from tilia.timelines.base.component.mixed import scale_mixed, crop_mixed
from tilia.timelines.base.validators import validate_string, validate_pre_validated
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.base.timeline import Timeline, TimelineComponentManager


class ScoreTLComponentManager(TimelineComponentManager):
    def __init__(self, timeline: ScoreTimeline):
        super().__init__(
            timeline,
            [
                ComponentKind.NOTE,
                ComponentKind.STAFF,
                ComponentKind.CLEF,
                ComponentKind.BAR_LINE,
                ComponentKind.TIME_SIGNATURE,
                ComponentKind.KEY_SIGNATURE,
                ComponentKind.SCORE_ANNOTATION,
            ],
        )
        self.scale = functools.partial(scale_mixed, self)
        self.crop = functools.partial(crop_mixed, self)

    def _validate_component_creation(self, kind, *args, **kwargs):
        match kind:
            # Validation of score components is much more complex than this.
            # Here we just check that the time is in bounds.
            # Proper validation on a class-by-class basis should be implemented at some point.
            case ComponentKind.NOTE:
                start = kwargs["start"] if "start" in kwargs else args[0]
                end = kwargs["end"] if "end" in kwargs else args[1]
                return SegmentLikeTimelineComponent.validate_times(start, end)
            case ComponentKind.CLEF | ComponentKind.BAR_LINE | ComponentKind.TIME_SIGNATURE | ComponentKind.KEY_SIGNATURE | ComponentKind.SCORE_ANNOTATION:
                time = kwargs["time"] if "time" in kwargs else args[0]
                return PointLikeTimelineComponent.validate_time_is_inbounds(time)
            case _:
                return True, ""

    def restore_state(self, prev_state: dict):
        super().restore_state(prev_state)
        post(Post.SCORE_TIMELINE_COMPONENTS_DESERIALIZED, self.timeline.id)

    def clear(self):
        super().clear()
        post(Post.SCORE_TIMELINE_CLEAR_DONE, self.timeline.id)


class ScoreTimeline(Timeline):
    KIND = TimelineKind.SCORE_TIMELINE
    SERIALIZABLE = [
        "height",
        "is_visible",
        "name",
        "ordinal",
        "svg_data",
        "viewer_beat_x",
    ]
    NOT_EXPORTABLE_ATTRS = ["svg_data", "viewer_beat_x"]
    COMPONENT_MANAGER_CLASS = ScoreTLComponentManager

    def __init__(
        self,
        svg_data: str = "",
        viewer_beat_x: dict[float, float] = {},
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.validators = self.validators | {
            "svg_data": validate_string,
            "viewer_beat_x": validate_pre_validated,
        }
        self._viewer_beat_x = viewer_beat_x
        self.svg_data = svg_data

    @property
    def svg_data(self):
        return self._svg_data

    @svg_data.setter
    def svg_data(self, svg_data):
        self._svg_data = svg_data

    @property
    def viewer_beat_x(self):
        return self._viewer_beat_x

    @viewer_beat_x.setter
    def viewer_beat_x(self, x_pos: dict[float, float] = {}):
        if x_pos:
            self._viewer_beat_x = x_pos

    def save_svg_data(self, svg_data):
        self._svg_data = svg_data

    @property
    def staff_count(self):
        return len(
            self.component_manager.get_existing_values_for_attr(
                "index", ComponentKind.STAFF
            )
        )

    def deserialize_components(self, components: dict[int, dict[str, Any]]):
        super().deserialize_components(components)
        post(Post.SCORE_TIMELINE_COMPONENTS_DESERIALIZED, self.id)
