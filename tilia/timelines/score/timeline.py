from __future__ import annotations

import functools
from typing import Any

from tilia.requests import Post, post
from tilia.timelines.base.component import (
    PointLikeTimelineComponent,
    SegmentLikeTimelineComponent,
)
from tilia.timelines.base.component.mixed import crop_mixed, scale_mixed
from tilia.timelines.base.timeline import (
    Timeline,
    TimelineComponentManager,
    TimelineFlag,
)
from tilia.timelines.base.validators import validate_pre_validated, validate_string
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.pcset import PitchClassSetAnalysis, analyse


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
                ComponentKind.NOTE_GROUP,
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
            case ComponentKind.CLEF | ComponentKind.BAR_LINE | ComponentKind.TIME_SIGNATURE | ComponentKind.KEY_SIGNATURE:
                time = kwargs["time"] if "time" in kwargs else args[0]
                return PointLikeTimelineComponent.validate_time_is_inbounds(time)
            case ComponentKind.SCORE_ANNOTATION | ComponentKind.STAFF | ComponentKind.NOTE_GROUP:
                # These do not have a time property.
                return True, ""
            case _:
                return False, "Invalid component kind."

    def restore_state(self, prev_state: dict):
        super().restore_state(prev_state)
        post(Post.SCORE_TIMELINE_COMPONENTS_DESERIALIZED, self.timeline.id)

    def clear(self):
        super().clear()
        # The score viewer is rebuilt from svg_data, so a cleared timeline
        # must not keep it: otherwise the viewer reopens with the discarded
        # score, both in this session and after saving and reloading.
        self.timeline.save_svg_data("")
        post(Post.SCORE_TIMELINE_CLEAR_DONE, self.timeline.id)


class ScoreTimeline(Timeline):
    SERIALIZABLE = [
        "height",
        "is_visible",
        "name",
        "ordinal",
        "svg_data",
        "viewer_beat_x",
        "score_text",
    ]
    NOT_EXPORTABLE_ATTRS = ["svg_data", "viewer_beat_x", "score_text"]
    COMPONENT_MANAGER_CLASS = ScoreTLComponentManager
    FLAGS = [
        TimelineFlag.COMPONENTS_COLORED,
        TimelineFlag.COMPONENTS_NOT_DELETABLE,
        TimelineFlag.COMPONENTS_IMPORTABLE,
    ]

    def __init__(
        self,
        svg_data: str = "",
        viewer_beat_x: dict[float, float] = None,
        score_text: str = "",
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.validators = self.validators | {
            "svg_data": validate_string,
            "viewer_beat_x": validate_pre_validated,
            "score_text": validate_string,
        }
        self._viewer_beat_x = viewer_beat_x or {}
        self.svg_data = svg_data
        # The score ScoreView shows, as imported.
        self.score_text = score_text

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
    def viewer_beat_x(self, x_pos: dict[float, float] | None = None):
        if x_pos:
            self._viewer_beat_x = x_pos

    def save_svg_data(self, svg_data):
        self._svg_data = svg_data

    def get_element_ids(self) -> dict[int, str]:
        """The element in the score of each note component that has one."""
        return {
            note.id: note.element_id
            for note in self.component_manager.get_components()
            if note.KIND == ComponentKind.NOTE and note.element_id
        }

    def analyse_elements(self, element_ids: list[str]) -> PitchClassSetAnalysis:
        """The pitch-class set of the score's notes with these elements.
        Unpitched notes have no pitch class."""
        wanted = set(element_ids)
        return analyse(
            note.sounding_pitch_class_24
            for note in self.component_manager.get_components()
            if note.KIND == ComponentKind.NOTE
            and note.element_id in wanted
            and note.is_pitched
        )

    def get_element_start_times(self, element_ids: list[str]) -> list[float]:
        """When the score's notes with these elements are first played: a
        repeated measure's element has a note for each time it's played."""
        wanted = set(element_ids)
        starts: dict[str, float] = {}
        for note in self.component_manager.get_components():
            if note.KIND == ComponentKind.NOTE and note.element_id in wanted:
                previous = starts.get(note.element_id, note.start)
                starts[note.element_id] = min(previous, note.start)
        return list(starts.values())

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
