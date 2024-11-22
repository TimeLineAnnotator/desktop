from __future__ import annotations

import functools
from pathlib import Path

from tilia.requests import post, Post
from tilia.timelines.base.component.mixed import scale_mixed, crop_mixed
from tilia.timelines.base.validators import validate_string
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.timeline import Timeline, TimelineComponentManager
from tilia.requests import get, Get


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


class ScoreTimeline(Timeline):
    KIND = TimelineKind.SCORE_TIMELINE
    SERIALIZABLE_BY_VALUE = ["height", "is_visible", "name", "ordinal", "svg_data"]
    COMPONENT_MANAGER_CLASS = ScoreTLComponentManager

    def __init__(self, svg_data: str = "", **kwargs):
        super().__init__(**kwargs)

        self.validators = self.validators | {"svg_data": validate_string}
        self.svg_data = svg_data

    @property
    def svg_data(self):
        return self._svg_data

    @svg_data.setter
    def svg_data(self, svg_data):
        self._svg_data = svg_data
        if svg_data:
            get(Get.TIMELINE_UI, self.id).svg_view.load_svg_data(svg_data)

    def save_svg_data(self, svg_data):
        self._svg_data = svg_data

    def mxl_updated(self, mxl_data):
        get(Get.TIMELINE_UI, self.id).svg_view.to_svg(mxl_data)

    @property
    def staff_count(self):
        return len(
            self.component_manager.get_existing_values_for_attr(
                "index", ComponentKind.STAFF
            )
        )

    def _validate_delete_components(self, components: list[TimelineComponent]) -> None:
        score_annotations = self.component_manager._get_component_set_by_kind(
            ComponentKind.SCORE_ANNOTATION
        )

        self._remove_from_viewer([s for s in score_annotations if s in components])

    def _remove_from_viewer(self, components: list[TimelineComponent]) -> None:
        for component in components:
            component.set_data("data", "delete")

    def deserialize_components(self, components: dict[int, dict[str]]):
        super().deserialize_components(components)
        post(Post.SCORE_TIMELINE_COMPONENTS_DESERIALIZED, self.id)
