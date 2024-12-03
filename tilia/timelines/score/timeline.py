from __future__ import annotations

import functools

from tilia.requests import post, Post
from tilia.timelines.base.component.mixed import scale_mixed, crop_mixed
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.timeline import Timeline, TimelineComponentManager


class ScoreTLComponentManager(TimelineComponentManager):
    def __init__(self, timeline: ScoreTimeline):
        super().__init__(timeline, [ComponentKind.NOTE, ComponentKind.STAFF, ComponentKind.CLEF, ComponentKind.BAR_LINE, ComponentKind.TIME_SIGNATURE, ComponentKind.KEY_SIGNATURE])
        self.scale = functools.partial(scale_mixed, self)
        self.crop = functools.partial(crop_mixed, self)


class ScoreTimeline(Timeline):
    KIND = TimelineKind.SCORE_TIMELINE
    COMPONENT_MANAGER_CLASS = ScoreTLComponentManager

    @property
    def staff_count(self):
        return len(self.component_manager.get_existing_values_for_attr('index', ComponentKind.STAFF))
    
    def _validate_delete_components(self, component: TimelineComponent) -> None:
        pass

    def deserialize_components(self, components: dict[int, dict[str]]):
        super().deserialize_components(components)
        post(Post.SCORE_TIMELINE_COMPONENTS_DESERIALIZED, self.id)


