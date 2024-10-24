from __future__ import annotations

import functools

from tilia.settings import settings
from tilia.timelines.base.common import scale_discrete, crop_discrete
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.timeline import Timeline, TimelineComponentManager


class ScoreTLComponentManager(TimelineComponentManager):
    def __init__(self, timeline: ScoreTimeline):
        super().__init__(timeline, [ComponentKind.NOTE, ComponentKind.STAFF, ComponentKind.CLEF])
        self.scale = functools.partial(scale_discrete, self)
        self.crop = functools.partial(crop_discrete, self)


class ScoreTimeline(Timeline):
    KIND = TimelineKind.SCORE_TIMELINE
    COMPONENT_MANAGER_CLASS = ScoreTLComponentManager

    @property
    def default_height(self):
        return settings.get("score_timeline", "default_height")
    
    def _validate_delete_components(self, component: TimelineComponent) -> None:
        pass


