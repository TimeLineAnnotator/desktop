from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any
from bisect import bisect

from tilia.exceptions import TimelineValidationError
from tilia.requests import Post, post, serve, Get, get, listen
from tilia.timelines.harmony.timeline import HarmonyTimeline, HarmonyTLComponentManager
from tilia.utils import get_tilia_class_string
from tilia.timelines.beat.timeline import BeatTimeline, BeatTLComponentManager
from tilia.timelines.marker.timeline import MarkerTimeline, MarkerTLComponentManager
from tilia.timelines.pdf.timeline import PdfTimeline, PdfTLComponentManager
from tilia.timelines.timeline_kinds import (
    TimelineKind as TlKind,
    TimelineKind,
    get_timeline_kind_from_string,
)
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.hierarchy.timeline import (
    HierarchyTimeline,
    HierarchyTLComponentManager,
)
from tilia.timelines.slider.timeline import SliderTimeline
from tilia.timelines.audiowave.timeline import (
    AudioWaveTimeline,
    AudioWaveTLComponentManager,
)
from tilia.undo_manager import PauseUndoManager

if TYPE_CHECKING:
    from tilia.app import App


def _create_hierarchy_timeline(**kwargs) -> HierarchyTimeline:
    component_manager = HierarchyTLComponentManager()
    timeline = HierarchyTimeline(component_manager, **kwargs)
    component_manager.associate_to_timeline(timeline)

    return timeline


def _create_slider_timeline(*_, **__) -> SliderTimeline:
    return SliderTimeline()


def _create_audiowave_timeline(*args, **kwargs) -> AudioWaveTimeline:
    component_manager = AudioWaveTLComponentManager()
    timeline = AudioWaveTimeline(component_manager, *args, **kwargs)
    component_manager.associate_to_timeline(timeline)

    return timeline


def _create_marker_timeline(*args, **kwargs) -> MarkerTimeline:
    component_manager = MarkerTLComponentManager()
    timeline = MarkerTimeline(component_manager, *args, **kwargs)
    component_manager.associate_to_timeline(timeline)

    return timeline


def _create_beat_timeline(*args, **kwargs) -> BeatTimeline:
    component_manager = BeatTLComponentManager()
    timeline = BeatTimeline(component_manager, *args, **kwargs)
    component_manager.associate_to_timeline(timeline)

    return timeline


def _create_harmony_timeline(*args, **kwargs) -> HarmonyTimeline:
    component_manager = HarmonyTLComponentManager()
    timeline = HarmonyTimeline(component_manager, *args, **kwargs)
    component_manager.associate_to_timeline(timeline)

    return timeline


def _create_pdf_timeline(*args, **kwargs) -> PdfTimeline:
    component_manager = PdfTLComponentManager()
    timeline = PdfTimeline(component_manager, *args, **kwargs)
    component_manager.associate_to_timeline(timeline)

    return timeline


class Timelines:
    def __init__(self, app: App):
        self._app = app
        self._timelines: list[Timeline] = []
        self.cached_media_duration = 0.0

        self._setup_requests()

    def __getitem__(self, key):
        return sorted(self._timelines)[key]

    def __iter__(self):
        return iter(self._timelines)

    def __str__(self):
        return get_tilia_class_string(self)

    def __len__(self):
        return len(self._timelines)

    def __bool__(self):
        return True  # so it doesn't evaluate to False when there are no timelines

    def _setup_requests(self):
        SERVES = {
            (Get.TIMELINE_COLLECTION, lambda: self),
            (Get.TIMELINES, self.get_timelines),
            (Get.TIMELINE, self.get_timeline),
            (Get.TIMELINE_ORDINAL_FOR_NEW, self.serve_ordinal_for_new_timeline),
            (Get.TIMELINE_BY_ATTR, self.get_timeline_by_attr),
            (Get.TIMELINES_BY_ATTR, self.get_timelines_by_attr),
            (Get.METRIC_POSITION, self.get_metric_position),
        }

        for request, callback in SERVES:
            serve(self, request, callback)

    @property
    def timeline_kinds(self):
        return {tl.KIND for tl in self._timelines}

    @property
    def is_empty(self):
        return len(self) == 0

    @property
    def is_blank(self):
        # a blank Timelines is empty or has a single slider timeline
        # which is its state when creating a new (blank) file
        return (
            self.is_empty
            or len(
                {x.KIND for x in self}.difference(
                    {TimelineKind.SLIDER_TIMELINE, TimelineKind.AUDIOWAVE_TIMELINE}
                )
            )
            == 0
        )

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

    def has_timeline_of_kind(self, kind: TlKind):
        return kind in self.timeline_kinds

    def create_timeline(
        self,
        kind: TlKind | str,
        components: dict[int, dict[str, Any]] | None = None,
        *args,
        **kwargs,
    ) -> Timeline | None:

        if isinstance(kind, str):
            kind = get_timeline_kind_from_string(kind)

        # has to be stored before timeline is created
        is_first_of_kind = kind not in self.timeline_kinds

        tl = {
            TlKind.HIERARCHY_TIMELINE: _create_hierarchy_timeline,
            TlKind.SLIDER_TIMELINE: _create_slider_timeline,
            TlKind.AUDIOWAVE_TIMELINE: _create_audiowave_timeline,
            TlKind.MARKER_TIMELINE: _create_marker_timeline,
            TlKind.BEAT_TIMELINE: _create_beat_timeline,
            TlKind.HARMONY_TIMELINE: _create_harmony_timeline,
            TlKind.PDF_TIMELINE: _create_pdf_timeline,
        }[kind](*args, **kwargs)
        self._add_to_timelines(tl)

        post(Post.TIMELINE_CREATE_DONE, kind, tl.id)

        if is_first_of_kind:
            post(Post.TIMELINE_KIND_INSTANCED, kind)

        if components:
            # can't be done until timeline UI has been created
            tl.deserialize_components(components)

        if hasattr(tl, "setup_blank_timeline") and not components:
            # For setup that needs to be done after
            # the corresponding timeline ui has
            # been created.
            tl.setup_blank_timeline()

        if kind == TlKind.AUDIOWAVE_TIMELINE and not components:
            tl.refresh()

        return tl

    def get_timeline(self, id: int) -> Timeline | None:
        return next((tl for tl in self._timelines if tl.id == id), None)

    def get_timelines(self):
        return sorted(self._timelines)

    def get_timeline_by_attr(self, attr: str, value: Any):
        return next((tl for tl in self if getattr(tl, attr) == value), None)

    def get_timelines_by_attr(self, attr: str, value: Any):
        return [tl for tl in self if getattr(tl, attr) == value]

    def set_timeline_data(self, id: int, attr: str, value: Any):
        timeline = self.get_timeline(id)
        if timeline.get_data(attr) == value:
            return
        value, success = self.get_timeline(id).set_data(attr, value)
        if success:
            post(Post.TIMELINE_SET_DATA_DONE, id, attr, value)

    def get_timeline_data(self, id: int, attr: str):
        return self.get_timeline(id).get_data(attr)

    def delete_timeline(self, timeline: Timeline):
        timeline.delete()
        self._remove_from_timelines(timeline)
        post(Post.TIMELINE_DELETE_DONE, timeline.id)

        if timeline.KIND not in self.timeline_kinds:
            post(Post.TIMELINE_KIND_NOT_INSTANCED, timeline.KIND)

    @staticmethod
    def clear_timeline(timeline: Timeline):
        timeline.clear()

    def clear_timelines(self):
        with PauseUndoManager():
            for timeline in self:
                timeline.clear()

    def _add_to_timelines(self, timeline: Timeline) -> None:
        self._timelines.append(timeline)
        # we don't have to update ordinal of any timeline because
        # we are inserting the new timeline at the end of the list
        # and giving it the next ordinal value

    def _remove_from_timelines(self, timeline: Timeline) -> None:
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
        return {tl.id: tl.get_state() for tl in self}

    def deserialize_timelines(self, data: dict) -> None:
        data_copy = copy.deepcopy(data)  # so pop does not modify original data

        for tl_data in data_copy.values():
            if "display_position" in tl_data:
                tl_data["ordinal"] = tl_data.pop("display_position") + 1
            kind = TimelineKind(tl_data.pop("kind"))
            self.create_timeline(kind, **tl_data)

    def restore_state(self, timeline_states: dict[str, dict]) -> None:
        id_to_timelines = {tl.id: tl for tl in self}
        shared_tl_ids = list(set(timeline_states) & set(id_to_timelines))

        # restore state of timelines that already exist
        for id in shared_tl_ids:
            self._restore_timeline_state(id_to_timelines[id], timeline_states[id])

        # delete timelines not in restored state
        for id in list(set(id_to_timelines) - set(shared_tl_ids)):
            self.delete_timeline(id_to_timelines[id])

        # create timelines that are only in restored state
        for id in list(set(timeline_states) - set(shared_tl_ids)):
            params = timeline_states[id].copy()
            kind = TimelineKind(params.pop("kind"))
            self.create_timeline(kind, **params)

    def _restore_timeline_state(self, timeline: Timeline, state: dict[str, dict]):
        timeline.clear()
        timeline.deserialize_components(state["components"])
        for attr in timeline.SERIALIZABLE_BY_VALUE:
            self.set_timeline_data(timeline.id, attr, state[attr])

    def get_timeline_ids(self):
        return [tl.id for tl in self]

    def has_timeline_of_kind(self, kind: TlKind):
        return any([tl.KIND == kind for tl in self])

    def serve_ordinal_for_new_timeline(self):
        return len(self._timelines) + 1

    def scale_timeline_components(self, factor: float) -> None:
        for tl in [tl for tl in self if hasattr(tl, "scale")]:
            tl.scale(factor)

    def crop_timeline_components(self, new_length: float) -> None:
        for tl in [tl for tl in self if hasattr(tl, "crop")]:
            tl.crop(new_length)
        post(Post.TIMELINES_CROP_DONE)

    def get_beat_timeline_for_measure_calculation(self):
        return sorted(self.get_timelines_by_attr("KIND", TimelineKind.BEAT_TIMELINE))[0]

    def get_metric_position(self, time: float):
        if not self.get_timelines_by_attr("KIND", TimelineKind.BEAT_TIMELINE):
            return None, None
        tl = self.get_beat_timeline_for_measure_calculation()
        beats = tl.components
        if not beats:
            return None, None
        times = [beat.get_data("time") for beat in beats]

        time_idx = bisect(times, time)  # returns the index where the time would go

        if time_idx == 0:
            closest_beat = beats[0]  # time is before first beat, get first beat
        elif time_idx == len(beats):
            closest_beat = beats[-1]  # time is after last beat, get last beat
        elif abs(time - times[time_idx - 1]) <= abs(time - times[time_idx]):
            closest_beat = beats[time_idx - 1]  # previous beat is closer
        else:
            closest_beat = beats[time_idx]  # next beat is closer

        return closest_beat.metric_position

    def clear(self):
        for timeline in self._timelines.copy():
            self.delete_timeline(timeline)
