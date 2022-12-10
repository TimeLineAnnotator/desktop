"""
Defines the TimelineCollection class, which compose the TiLiA class.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any

from tilia.events import subscribe, Event
from tilia.timelines.timeline_kinds import TimelineKind

if TYPE_CHECKING:
    from tilia.main import TiLiA

import logging

logger = logging.getLogger(__name__)

from tilia import globals_, events
from tilia.timelines.common import Timeline
from tilia.timelines.hierarchy.timeline import (
    HierarchyTimeline,
    HierarchyTLComponentManager,
)

from tilia.timelines.slider import SliderTimeline


class TimelineCollection:
    """Collection of Timeline objects. Handles timeline creation
    and handles timelines request for "global" data (e.g. media length).
    """

    def __init__(self, app: TiLiA):
        self._app = app
        self._timelines = []
        self._timeline_ui_collection = None  # will be set by TiLiA

        subscribe(self, Event.PLAYER_MEDIA_LOADED, self.on_media_loaded)

    def create_timeline(self, timeline_kind: TimelineKind, **kwargs) -> Timeline:
        if timeline_kind == TimelineKind.HIERARCHY_TIMELINE:
            tl = self._create_hierarchy_timeline(**kwargs)
        elif timeline_kind == TimelineKind.SLIDER_TIMELINE:
            tl = self._create_slider_timeline()
        else:
            raise NotImplementedError

        self._timelines.append(tl)

        return tl

    def _create_hierarchy_timeline(self, **kwargs) -> HierarchyTimeline:
        component_manager = HierarchyTLComponentManager()
        timeline = HierarchyTimeline(self, component_manager, **kwargs)
        component_manager.associate_to_timeline(timeline)

        return timeline

    def _create_slider_timeline(self):
        return SliderTimeline(self, None, TimelineKind.SLIDER_TIMELINE)

    def delete_timeline(self, timeline: Timeline):
        logger.debug(f"Deleting timeline {timeline}")
        timeline.delete()
        self._timeline_ui_collection.delete_timeline_ui(timeline.ui)

    def _add_to_timelines(self, timeline: Timeline) -> None:
        logger.debug(f"Adding component '{timeline}' to {self}.")
        self._timelines.append(timeline)

    def _remove_from_timelines(self, timeline: Timeline) -> None:
        logger.debug(f"Removing timeline '{timeline}' to {self}.")
        try:
            self._timelines.remove(timeline)
        except ValueError:
            raise ValueError(
                f"Can't remove timeline '{timeline}' from {self}: not in self._timelines."
            )

    def serialize_timelines(self):
        logger.debug(f"Serializing all timelines...")
        return {tl.id: tl.to_dict() for tl in self._timelines}

    def get_timeline_by_id(self, id_: int) -> Timeline:
        return next((e for e in self._timelines if e.id == id_), None)

    def get_timeline_attribute_by_id(self, id_: int, attribute: str) -> Any:
        timeline = self.get_timeline_by_id(id_)
        return getattr(timeline, attribute)

    def get_timeline_ids(self):
        return [tl.id for tl in self._timelines]

    def get_id(self) -> str:
        return self._app.get_id()

    def get_media_length(self):
        return self._app.media_length

    def get_current_playback_time(self):
        return self._app.current_playback_time

    def has_slider_timeline(self):
        return any([isinstance(SliderTimeline, tl) for tl in self._timelines])

    def has_timeline_of_kind(self, kind: TimelineKind):
        return any([tl.KIND == kind for tl in self._timelines])

    def on_media_loaded(self, _1, new_media_length: float, _2, previous_media_length: float):
        if not self.has_timeline_of_kind(TimelineKind.HIERARCHY_TIMELINE):
            return

        events.post(Event.REQUEST_CHANGE_TIMELINE_WIDTH, self._timeline_ui_collection.get_timeline_width() * new_media_length / previous_media_length)

        SCALE_HIERARCHIES_PROMPT = "Would you like to scale the hierarchies to new media's length?"
        CROP_HIERARCHIES_PROMPT = "New media is smaller, so " \
                                  "any hierarchies that exceed its size will be deleted or cropped."\
                                  "Are you sure you don't want to scale them instead?"

        if not self._app.ui.ask_yes_no(
                'Scale hierarchies',
                SCALE_HIERARCHIES_PROMPT
        ):
            self.scale_components_by_timeline_kind(TimelineKind.HIERARCHY_TIMELINE, new_media_length / previous_media_length)

        elif new_media_length < previous_media_length:
            if self._app.ui.ask_yes_no(
                    'Confirm crop hierarchies',
                    CROP_HIERARCHIES_PROMPT
            ):
                self.crop_components_by_timeline_kind(TimelineKind.HIERARCHY_TIMELINE, new_media_length)
            else:
                self.scale_components_by_timeline_kind(TimelineKind.HIERARCHY_TIMELINE, new_media_length / previous_media_length)

        self.update_ui_elements_position_by_timeline_kind(TimelineKind.HIERARCHY_TIMELINE)


    def scale_components_by_timeline_kind(self, kind: TimelineKind, factor: float) -> None:
        for tl in [tl for tl in self._timelines if tl.KIND == kind]:
            tl.scale(factor)

    def crop_components_by_timeline_kind(self, kind: TimelineKind, new_length: float) -> None:
        for tl in [tl for tl in self._timelines if tl.KIND == kind]:
            tl.crop(new_length)

    def update_ui_elements_position_by_timeline_kind(self, kind: TimelineKind) -> None:
        for tl in [tl for tl in self._timelines if tl.KIND == kind]:
            tl.ui.update_elements_position()


    def clear(self):
        logger.debug(f"Clearing timeline collection...")
        for timeline in self._timelines.copy():
            timeline.delete()
            self._remove_from_timelines(timeline)
            self._timeline_ui_collection.delete_timeline_ui(timeline.ui)

    def from_dict(self, timelines_dict: dict[dict]) -> None:
        sort_attribute = ["display_position"]

        sorted_timelines_dict = sorted(timelines_dict.items(), key=lambda _, tl_dict: getattr(tl_dict, sort_attribute))

        for _, tl_dict in sorted_timelines_dict:
            tl_kind = TimelineKind[tl_dict.pop("kind")]
            self.create_timeline(tl_kind, **tl_dict)
