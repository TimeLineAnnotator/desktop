from __future__ import annotations

import functools

from tilia.timelines.base.common import scale_discrete, crop_discrete
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.base.component import TimelineComponent
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
            ],
        )
        self.scale = functools.partial(scale_discrete, self)
        self.crop = functools.partial(crop_discrete, self)


class ScoreTimeline(Timeline):
    KIND = TimelineKind.SCORE_TIMELINE
    COMPONENT_MANAGER_CLASS = ScoreTLComponentManager

    @property
    def staff_count(self):
        return len(
            self.component_manager.get_existing_values_for_attr(
                "index", ComponentKind.STAFF
            )
        )

    def _validate_delete_components(self, component: TimelineComponent) -> None:
        pass
