from __future__ import annotations
from typing import TYPE_CHECKING, Any
import logging

from tilia.exceptions import TimelineValidationError
from tilia.requests import Post, post, serve, Get, get
from tilia.repr import default_str
from tilia.requests.post import listen_to_multiple
from tilia.timelines.beat.timeline import BeatTimeline, BeatTLComponentManager
from tilia.timelines.marker.timeline import MarkerTimeline, MarkerTLComponentManager
from tilia.timelines.state_actions import Action
from tilia.timelines.timeline_kinds import TimelineKind as TlKind
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.hierarchy.timeline import (
    HierarchyTimeline,
    HierarchyTLComponentManager,
)
from tilia.timelines.slider.timeline import SliderTimeline

if TYPE_CHECKING:
    from tilia.app import App
    from tilia.timelines.base.component import TimelineComponent

logger = logging.getLogger(__name__)


def _create_hierarchy_timeline(**kwargs) -> HierarchyTimeline:
    component_manager = HierarchyTLComponentManager()
    timeline = HierarchyTimeline(component_manager, **kwargs)
    component_manager.associate_to_timeline(timeline)

    return timeline


def _create_slider_timeline(**_) -> SliderTimeline:
    return SliderTimeline()


def _create_marker_timeline(**kwargs) -> MarkerTimeline:
    component_manager = MarkerTLComponentManager()
    timeline = MarkerTimeline(component_manager, **kwargs)
    component_manager.associate_to_timeline(timeline)

    return timeline


def _create_beat_timeline(beat_pattern=None, **kwargs) -> BeatTimeline:
    component_manager = BeatTLComponentManager()
    if not beat_pattern:
        beat_pattern = get(Get.BEAT_PATTERN_FROM_USER)
        if not beat_pattern:
            raise ValueError("User cancelled timeline creation.")

    timeline = BeatTimeline(component_manager, beat_pattern, **kwargs)

    component_manager.associate_to_timeline(timeline)

    return timeline


class Timelines:
    """
    Collection of Timeline objects.
    """

    def __init__(self, app: App):
        self._app = app
        self._timelines = []

        listen_to_multiple(
            self,
            [
                (Post.PLAYER_MEDIA_LOADED, self.on_media_loaded),
                (Post.REQUEST_TIMELINE_CREATE, self.create_timeline),
                (Post.REQUEST_TIMELINE_DELETE, self.on_request_timeline_delete),
                (Post.REQUEST_TIMELINE_CLEAR, self.on_request_timeline_delete),
                (Post.REQUEST_TIMELINE_CLEAR_ALL, self.clear_all_timelines),
                (Post.REQUEST_MOVE_TIMELINE_DOWN_IN_ORDER, self.on_move_down_in_order),
                (Post.REQUEST_MOVE_TIMELINE_UP_IN_ORDER, self.on_move_up_in_order),
                (Post.COMPONENT_CREATE_REQUEST, self.on_component_create_request),
            ],
        )

        serve(self, Get.TIMELINES, self.get_timelines)
        serve(self, Get.TIMELINE, self.get_timeline)
        serve(
            self,
            Get.ORDINAL_FOR_NEW_TIMELINE,
            self.serve_ordinal_for_new_timeline,
        )
        serve(self, Get.TIMELINE_BY_ATTR, self.get_timeline_by_attr)
        serve(self, Get.TIMELINES_BY_ATTR, self.get_timelines_by_attr)

    def __getitem__(self, key):
        return self._timelines[key]

    def __iter__(self):
        return iter(self._timelines)

    def __str__(self):
        return default_str(self)

    def __len__(self):
        return len(self._timelines)

    def __bool__(self):
        return True  # so it doesn't evaluate to False when there are no timelines

    @property
    def timeline_kinds(self):
        return {tl.KIND for tl in self._timelines}

    @staticmethod
    def _validate_timeline_kind(kind: TlKind | str):
        if isinstance(kind, str):
            try:
                kind = TlKind(kind)
            except ValueError:
                raise TimelineValidationError(
                    f"Can't create timeline: invalid timeline kind '{kind}'"
                )
        if not isinstance(kind, TlKind):
            raise TimelineValidationError(
                f"Can't create timeline: invalid timeline kind '{kind}'"
            )

        return kind

    def create_timeline(
        self,
        kind: TlKind | str,
        ask_user_for_name: bool = True,
        components: dict[int, TimelineComponent] = None,
        **kwargs,
    ) -> Timeline:
        try:
            kind = self._validate_timeline_kind(kind)
        except TimelineValidationError:
            post(
                Post.REQUEST_DISPLAY_ERROR,
                "Timeline creation error",
                f"Can't create timeline. Got invalid kind {kind}",
            )

        if (
            ask_user_for_name
            and "name" not in kwargs
            and kind != TlKind.SLIDER_TIMELINE
        ):
            kwargs["name"] = get(
                Get.STRING_FROM_USER,
                title="Name for new timeline",
                prompt="Choose name for new timeline",
            )

        kind_to_callback = {
            TlKind.HIERARCHY_TIMELINE: _create_hierarchy_timeline,
            TlKind.SLIDER_TIMELINE: _create_slider_timeline,
            TlKind.MARKER_TIMELINE: _create_marker_timeline,
            TlKind.BEAT_TIMELINE: _create_beat_timeline,
        }

        # has to be check before timeline is created
        is_first_of_kind = kind not in self.timeline_kinds

        tl = kind_to_callback[kind](**kwargs)
        self._add_to_timelines(tl)

        post(Post.TIMELINE_CREATED, kind, tl.id)

        if is_first_of_kind:
            post(Post.TIMELINE_KIND_INSTANCED, kind)

        if components:
            # can't be done untial timeline UI has been created
            tl.deserialize_components(components)

        if kind == TlKind.HIERARCHY_TIMELINE and not components:
            tl.create_initial_hierarchy()
            # so user has a starting hierarchy to split
            # can't be done until timeline UI has been created

        post(Post.REQUEST_RECORD_STATE, Action.TIMELINE_CREATE)

        return tl

    def get_timeline(self, id: str) -> Timeline | None:
        return next((tl for tl in self._timelines if tl.id == id), None)

    def get_timelines(self):
        return self._timelines

    def get_timeline_by_attr(self, attr: str, value: Any):
        return next((tl for tl in self._timelines if getattr(tl, attr) == value), None)

    def get_timelines_by_attr(self, attr: str, value: Any):
        return [tl for tl in self._timelines if getattr(tl, attr) == value]

    def on_request_timeline_delete(self, id: str):
        self.delete_timeline(self.get_timeline(id))

    def delete_timeline(self, timeline: Timeline):
        logger.info(f"Deleting timeline {timeline}")
        timeline.delete()
        self._timelines.remove(timeline)
        post(Post.TIMELINE_DELETED, timeline.id)

        if timeline.KIND not in self.timeline_kinds:
            post(Post.TIMELINE_KIND_UNINSTANCED, timeline.KIND)

    def on_request_timeline_clear(self, id: str):
        self.clear_timeline(self.get_timeline(id))

    @staticmethod
    def clear_timeline(timeline: Timeline):
        logger.info(f"Clearing timeline {timeline}...")
        timeline.clear()

        post(Post.REQUEST_RECORD_STATE, Action.CLEAR_TIMELINE)

    def clear_all_timelines(self):
        logger.info("Clearing all timelines...")
        for timeline in self:
            timeline.clear()

        post(Post.REQUEST_RECORD_STATE, Action.CLEAR_ALL_TIMELINES)

    def on_component_create_request(self, tl_id: str, *args, **kwargs):
        self.get_timeline(tl_id).create_timeline_component(*args, **kwargs)

    def _add_to_timelines(self, timeline: Timeline) -> None:
        logger.debug(f"Adding component '{timeline}' to {self}.")
        self._timelines.append(timeline)
        # we don't have to update ordinal of any timeline because
        # we are inserting the new timeline at the end of the list
        # and giving it the next ordinal value

    def _remove_from_timelines(self, timeline: Timeline) -> None:
        logger.debug(f"Removing timeline '{timeline}' from {self}.")
        try:
            self._timelines.remove(timeline)
            # update ordinal of all timelines that came after the removed timeline
            for tl in self:
                if tl.ordinal > timeline.ordinal:
                    tl.ordinal -= 1
        except ValueError:
            raise ValueError(
                f"Can't remove timeline '{timeline}' from {self}: not in"
                " self._timelines."
            )

    def serialize_timelines(self):
        logger.debug("Serializing all timelines...")
        return {tl.id: tl.get_state() for tl in self}

    def deserialize_timelines(self, data: dict) -> None:
        for tl_data in data.values():
            self.create_timeline(ask_user_for_name=False, **tl_data)

    def restore_state(self, timeline_states: dict[str, dict]) -> None:
        def _delete_timeline_ui_with_workaround(timeline):
            timeline_delete_func = timeline.ui.delete
            timeline.ui.delete = timeline.ui.delete_workaround_with_grid_forget
            self.delete_timeline(id_to_timelines[id])
            timeline.ui.delete = timeline_delete_func

        id_to_timelines = {tl.id: tl for tl in self}
        shared_tl_ids = list(set(timeline_states) & set(id_to_timelines))

        # restore state of timelines that already exist
        for id in shared_tl_ids:
            id_to_timelines[id].restore_state(timeline_states[id])

        # delete timelines not in restored state
        for id in list(set(id_to_timelines) - set(shared_tl_ids)):
            _delete_timeline_ui_with_workaround(id_to_timelines[id])

        # create timelines that are only in restored state
        for id in list(set(timeline_states) - set(shared_tl_ids)):
            params = timeline_states[id].copy()
            self.create_timeline(**params)

        post(Post.TIMELINE_COLLECTION_STATE_RESTORED)

    def get_timeline_ids(self):
        return [tl.id for tl in self]

    def has_timeline_of_kind(self, kind: TlKind):
        return any([tl.KIND == kind for tl in self])

    def on_media_loaded(
        self, _1, new_media_length: float, _2, previous_media_length: float
    ):
        if not self.has_timeline_of_kind(TlKind.HIERARCHY_TIMELINE):
            return

        post(
            Post.REQUEST_CHANGE_TIMELINE_WIDTH,
            get(Get.TIMELINE_WIDTH) * new_media_length / previous_media_length,
        )

        logger.debug("Asking user if scale timelines is wanted...")
        SCALE_HIERARCHIES_PROMPT = (
            "Would you like to scale existing timelines to new media length?"
        )

        if get(Get.YES_OR_NO_FROM_USER, "Scale timelines", SCALE_HIERARCHIES_PROMPT):
            logger.debug("User chose to scale timelines.")
            self.scale_timeline_components(
                new_media_length / previous_media_length,
            )

        elif new_media_length < previous_media_length:
            logger.debug(
                "User chose not to scale timelines. Asking is timelin crop is wanted..."
            )
            CROP_HIERARCHIES_PROMPT = (
                "New media is smaller, "
                "so components may get deleted or cropped. "
                "Are you sure you don't want to scale existing timelines?"
            )
            if get(Get.YES_OR_NO_FROM_USER, "Crop timelines", CROP_HIERARCHIES_PROMPT):
                logger.debug("User chose to crop timelines.")
                self.crop_timeline_components(new_media_length)
            else:
                logger.debug("User chose not to crop timelines.")
                self.scale_timeline_components(
                    new_media_length / previous_media_length,
                )

    def serve_ordinal_for_new_timeline(self):
        return len(self._timelines) + 1

    def on_move_up_in_order(self, id: str):
        timeline = self.get_timeline(id)
        timeline_above = [tl for tl in self if tl.ordinal == timeline.ordinal - 1][0]
        self.swap_timeline_order(timeline, timeline_above)

    def on_move_down_in_order(self, id: str):
        timeline = self.get_timeline(id)
        timeline_below = [tl for tl in self if tl.ordinal == timeline.ordinal + 1][0]
        self.swap_timeline_order(timeline, timeline_below)

    @staticmethod
    def swap_timeline_order(tl1: Timeline, tl2: Timeline):
        tl1.ordinal, tl2.ordinal = tl2.ordinal, tl1.ordinal
        post(Post.TIMELINE_ORDER_SWAPPED, tl1.id, tl2.id)

    def scale_timeline_components(self, factor: float) -> None:
        for tl in [tl for tl in self if hasattr(tl, "scale")]:
            tl.scale(factor)

    def crop_timeline_components(self, new_length: float) -> None:
        for tl in [tl for tl in self if hasattr(tl, "scale")]:
            tl.crop(new_length)

    def update_ui_elements_position_by_timeline_kind(self, kind: TlKind) -> None:
        for tl in [tl for tl in self if tl.KIND == kind]:
            tl.ui.update_elements_position()

    def clear(self):
        logger.debug("Clearing timeline collection...")
        for timeline in self._timelines.copy():
            self.delete_timeline(timeline)
