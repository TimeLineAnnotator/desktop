from __future__ import annotations

import functools
from pathlib import Path

from tilia.timelines.base.common import scale_discrete, crop_discrete
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.timeline import Timeline, TimelineComponentManager
from tilia.requests import get, Get
from tilia.timelines.base.validators import validate_string


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.validators = self.validators | {"path": validate_string}
        self._path = None

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, path: Path):
        self._path = path
        get(Get.TIMELINE_UI, self.id).path_updated(path)

    @property
    def staff_count(self):
        return len(
            self.component_manager.get_existing_values_for_attr(
                "index", ComponentKind.STAFF
            )
        )

    def _validate_delete_components(self, component: TimelineComponent) -> None:
        pass
