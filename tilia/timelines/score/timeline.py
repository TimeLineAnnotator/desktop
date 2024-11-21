from __future__ import annotations

import functools
from pathlib import Path

from tilia.timelines.base.common import scale_discrete, crop_discrete
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
                ComponentKind.SCORE_VIEWER,
                ComponentKind.SCORE_ANNOTATION,
            ],
        )
        self.scale = functools.partial(scale_discrete, self)
        self.crop = functools.partial(crop_discrete, self)


class ScoreTimeline(Timeline):
    KIND = TimelineKind.SCORE_TIMELINE
    COMPONENT_MANAGER_CLASS = ScoreTLComponentManager

    def path_updated(self, path: Path):
        if not (
            score_svg := self.component_manager._get_component_set_by_kind(
                ComponentKind.SCORE_VIEWER
            )
        ):
            (score_svg, _) = self.create_component(
                kind=ComponentKind.SCORE_VIEWER, start=0, end=get(Get.MEDIA_DURATION)
            )
        else:
            score_svg = list(score_svg)[0]
        score_svg.path_updated(path)

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
        if (
            score_svg := self.component_manager._get_component_set_by_kind(
                ComponentKind.SCORE_VIEWER
            )
        ) and list(score_svg)[0] in components:
            self.delete_components(
                [s for s in score_annotations if s not in components]
            )
            get(Get.TIMELINE_UI, self.id).delete_svg_view()

        self._remove_from_viewer([s for s in score_annotations if s in components])

    def _remove_from_viewer(self, components: list[TimelineComponent]) -> None:
        for component in components:
            component.set_data("data", "delete")
