"""
Defines the TimelineCollection class, which compose the TiLiA class.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Any

from tilia.events import subscribe, Event
from tilia.timelines.beat.timeline import BeatTimeline, BeatTLComponentManager
from tilia.timelines.marker.timeline import MarkerTimeline, MarkerTLComponentManager
from tilia.timelines.timeline_kinds import TimelineKind


if TYPE_CHECKING:
    from tilia.main import TiLiA
    from tilia.ui.timelines.collection import TimelineUICollection

import logging

logger = logging.getLogger(__name__)

from tilia import events
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
        match timeline_kind:
            case TimelineKind.HIERARCHY_TIMELINE:
                tl = self._create_hierarchy_timeline(**kwargs)
            case TimelineKind.SLIDER_TIMELINE:
                tl = self._create_slider_timeline()
            case TimelineKind.MARKER_TIMELINE:
                tl = self._create_marker_timeline(**kwargs)
            case TimelineKind.BEAT_TIMELINE:
                tl = self._create_beat_timeline(**kwargs)
            case _:
                raise NotImplementedError

        self._timelines.append(tl)

        return tl

    def _create_hierarchy_timeline(self, **kwargs) -> HierarchyTimeline:
        component_manager = HierarchyTLComponentManager()
        timeline = HierarchyTimeline(self, component_manager, **kwargs)
        component_manager.associate_to_timeline(timeline)

        return timeline

    def _create_slider_timeline(self) -> SliderTimeline:
        return SliderTimeline(self, None, TimelineKind.SLIDER_TIMELINE)

    def _create_marker_timeline(self, **kwargs) -> MarkerTimeline:
        component_manager = MarkerTLComponentManager()
        timeline = MarkerTimeline(self, component_manager, **kwargs)
        component_manager.associate_to_timeline(timeline)

        return timeline

    def _create_beat_timeline(self, beat_pattern=None, **kwargs) -> BeatTimeline:
        component_manager = BeatTLComponentManager()
        if not beat_pattern:
            beat_pattern = self._timeline_ui_collection.ask_beat_pattern()
            if not beat_pattern:
                raise ValueError("User cancelled timeline creation.")

        timeline = BeatTimeline(self, component_manager, beat_pattern, **kwargs)

        component_manager.associate_to_timeline(timeline)

        return timeline

    def delete_timeline(self, timeline: Timeline):
        logger.debug(f"Deleting timeline {timeline}")
        timeline.delete()
        self._timeline_ui_collection.delete_timeline_ui(timeline.ui)
        self._timelines.remove(timeline)

    @staticmethod
    def clear_timeline(timeline: Timeline):
        logger.debug(f"Clearing timeline {timeline}")
        timeline.clear()

    def _add_to_timelines(self, timeline: Timeline) -> None:
        logger.debug(f"Adding component '{timeline}' to {self}.")
        self._timelines.append(timeline)

    def _remove_from_timelines(self, timeline: Timeline) -> None:
        logger.debug(f"Removing timeline '{timeline}' from {self}.")
        try:
            self._timelines.remove(timeline)
        except ValueError:
            raise ValueError(
                f"Can't remove timeline '{timeline}' from {self}: not in self._timelines."
            )

    def serialize_timelines(self):
        logger.debug(f"Serializing all timelines...")
        return {tl.id: tl.get_state() for tl in self._timelines}

    def restore_state(self, timeline_states: dict[dict]) -> None:
        def _delete_timeline_ui_with_workaround(timeline):
            timeline_delete_func = timeline.ui.delete
            timeline.ui.delete = timeline.ui.delete_workaround_with_grid_forget
            self.delete_timeline(id_to_timelines[id])
            timeline.ui.delete = timeline_delete_func

        id_to_timelines = {tl.id: tl for tl in self._timelines}
        shared_tl_ids = list(set(timeline_states) & set(id_to_timelines))

        # restore state of timelines that already exist
        for id in shared_tl_ids:
            id_to_timelines[id].restore_state(timeline_states[id])

        # delete timelines not in restored state
        for id in list(set(id_to_timelines) - set(shared_tl_ids)):
            _delete_timeline_ui_with_workaround(id_to_timelines[id])

        # create timelines only in restored state
        for id in list(set(timeline_states) - set(shared_tl_ids)):
            from tilia.timelines.create import create_timeline

            params = timeline_states[id].copy()
            timeline_kind = TimelineKind[params.pop("kind")]
            create_timeline(timeline_kind, self, self._timeline_ui_collection, **params)

        self._timeline_ui_collection.after_restore_state()

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

    def on_media_loaded(
        self, _1, new_media_length: float, _2, previous_media_length: float
    ):
        if not self.has_timeline_of_kind(TimelineKind.HIERARCHY_TIMELINE):
            return

        events.post(
            Event.REQUEST_CHANGE_TIMELINE_WIDTH,
            self._timeline_ui_collection.get_timeline_width()
            * new_media_length
            / previous_media_length,
        )

        SCALE_HIERARCHIES_PROMPT = (
            "Would you like to scale the hierarchies to new media's length?"
        )
        CROP_HIERARCHIES_PROMPT = (
            "New media is smaller, "
            "so hierarchies may get deleted or cropped. "
            "Are you sure you don't want to scale them instead?"
        )

        if self._app.ui.ask_yes_no("Scale hierarchies", SCALE_HIERARCHIES_PROMPT):
            self.scale_components_by_timeline_kind(
                TimelineKind.HIERARCHY_TIMELINE,
                new_media_length / previous_media_length,
            )

        elif new_media_length < previous_media_length:
            if self._app.ui.ask_yes_no(
                "Confirm crop hierarchies", CROP_HIERARCHIES_PROMPT
            ):
                self.crop_components_by_timeline_kind(
                    TimelineKind.HIERARCHY_TIMELINE, new_media_length
                )
            else:
                self.scale_components_by_timeline_kind(
                    TimelineKind.HIERARCHY_TIMELINE,
                    new_media_length / previous_media_length,
                )

        self.update_ui_elements_position_by_timeline_kind(
            TimelineKind.HIERARCHY_TIMELINE
        )

    def scale_components_by_timeline_kind(
        self, kind: TimelineKind, factor: float
    ) -> None:
        for tl in [tl for tl in self._timelines if tl.KIND == kind]:
            tl.scale(factor)

    def crop_components_by_timeline_kind(
        self, kind: TimelineKind, new_length: float
    ) -> None:
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

    def __str__(self):
        return self.__class__.__name__ + f"({id(self)})"
