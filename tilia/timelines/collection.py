"""
Defines the TimelineCollection class, which compose the TiLiA class.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from tilia.timelines.timeline_kinds import TimelineKind

if TYPE_CHECKING:
    from tilia.main import TiLiA

import sys
import logging

logger = logging.getLogger(__name__)

import tkinter as tk
from tkinter import messagebox

from tilia import globals_
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

    def get_id(self):
        return self._app.get_id()

    def get_media_length(self):
        return self._app.media_length

    def get_current_playback_time(self):
        return self._app.current_playback_time

    def clear(self):
        logger.debug(f"Clearing timeline collection...")
        for timeline in self._timelines.copy():
            timeline.delete()
            timeline.ui.delete()
            self._remove_from_timelines(timeline)

    def from_dict(self, timelines_dict: dict[dict]) -> None:
        for _, tl_dict in timelines_dict.items():
            tl_kind = TimelineKind[tl_dict.pop("kind")]
            self.create_timeline(tl_kind, **tl_dict)


# noinspection PyTypeChecker,PyUnresolvedReferences
class TimelineCollectionOldMethods:
    """Old timeline collection methods kept here for ease of reference.
    Will be removed soon."""

    def load_timeline(self, tl_type: str, tl_dict: dict) -> None:
        def _update_main_objects_collection_key_name(tl_dict) -> dict:
            if "main_objects" in tl_dict.keys():
                tl_dict["main_objects_collection"] = tl_dict["main_objects"]
                del tl_dict["main_objects"]

            return tl_dict

        def _load_hierarchy_timeline(tl_dict) -> None:
            from tilia.timelines.hierarchy.timeline import (
                HierarchyTimeline,
            )  # HierachyTimeline has been refactored to another module

            tl_dict = _update_main_objects_collection_key_name(tl_dict)
            HierarchyTimeline(collection=self, **tl_dict)

        if tl_type == "HierarchyTimeline":
            _load_hierarchy_timeline(tl_dict)
            return

        getattr(sys.modules[__name__], tl_type)(collection=self, **tl_dict)

    def remove_by_id(self, timeline_id):
        """Deletes timeline by id"""
        timeline = [t for t in self.objects if t.collection_id == timeline_id][0]
        timeline.delete()
        logger.info(f"Deleted timeline {timeline}")

    def clear_by_id(self, timeline_id):
        """Deletes timeline by id"""
        timeline = [t for t in self.objects if t.collection_id == timeline_id][0]
        timeline.clear()

    def ask_clear_all(self):
        response = messagebox.askquestion(
            "Clear allt timeline",
            f"Are you sure you want to clear all timelines?\n"
            f"THIS CANNOT BE UNDONE.",
        )
        if response == "yes":
            self.clear_all()

    def clear_all(self):
        for timeline in self.objects:
            timeline.clear()

    def __len__(self):
        """Return number of children Timeline() objects"""
        return len(self.objects)

    def __repr__(self):
        return f"{self.__class__}"

    def find_by_class(self, my_class):
        """Returns a list of children Timeline() objects of my_class"""
        return [t for t in self.objects if isinstance(t, my_class)]

    def find_by_canvas(self, canvas):
        """Returns the timeline to which canvas belongs"""
        for timeline in self.objects:
            if timeline.canvas == canvas:
                return timeline

    def clear(self):
        """Clear all children Timeline() objects"""
        for timeline in self.objects:
            timeline.clear()

    def delete_timelines(self):
        """Delete all children Timeline objects"""
        for timeline in self.objects.copy():
            timeline.delete()

    def rearrange(self):
        """Arranges timeline vertically according to self.list order"""
        for index, timeline in enumerate(self.objects):
            timeline.grid_row = index
            timeline.make_invisible(change_visibility=False)
            if timeline.visible:
                timeline.make_visible()

    def update_select_order(self, timeline):
        """Sends given timeline to top of selecting order"""
        if timeline in self.select_order:
            self.select_order.remove(timeline)

        self.select_order.insert(0, timeline)

    def subscriber_react(self, event_name: str, *args: tuple, **kwargs: dict) -> None:

        if event_name == "LEFT_BUTTON_CLICK":
            canvas: tk.Canvas = args[0]
            timeline = self.find_by_canvas(canvas)
            self.update_select_order(timeline)
        elif event_name == "RIGHT_BUTTON_CLICK":
            event: tk.Event = args[0]
            timeline = self.find_by_canvas(event.widget)
            canvas_id = next(iter(timeline.canvas.find_withtag(tk.CURRENT)), None)
            timeline.on_right_click(canvas_id, event)
        elif event_name == "PLAYER: STOPPED":
            self.update_vlines_position(0)
        elif event_name == "PLAYER: CURRENT TIME CHANGE":
            self.update_vlines_position(args[0])
        elif event_name == "PLAYER: MEDIA LOADED":
            if self.objects:
                self.fix_misaligned_timelines()
        elif event_name == "FREEZE_LABELS_SET":
            self.reset_labels_position()
        elif event_name == "ENTER_PRESSED":
            self.on_enter_pressed()
        elif event_name == "FOCUS_TIMELINES":
            self.on_focus_timelines()
        elif event_name == "REQUEST: TIMELINE FRONTEND - RESET TIMELINE SIZE":
            self.on_reset_timeline_size()
        elif event_name == "REQUEST: TIMELINES - LOAD TIMELINE":
            self.load_timeline(*args)

    @staticmethod
    def on_reset_timeline_size():
        globals_.TIMELINE_XSIZE = 3000

    @staticmethod
    def on_enter_pressed():
        if globals_.SELECTED_OBJECTS:
            if not globals_.INSPECTOR:
                globals_.APP.start_inspector()
            else:
                globals_.INSPECTOR.take_focus()

    def on_focus_timelines(self):
        self.select_order[0].canvas.focus_set()

    def draw_vertical_lines(self):
        for timeline in self.objects:
            timeline.draw_vertical_line()

    def update_vlines_position(self, time: float) -> None:
        for timeline in self.objects:
            timeline.update_vline_position(time)

    def update_labels_position(self):
        for timeline in self.objects:
            timeline.update_freezed_label_position()

    def reset_labels_position(self) -> None:
        for timeline in self.objects:
            timeline.reset_label_position()

    def get_all_selected_objects(self):
        selected = []
        for timeline in self.objects:
            selected += timeline.selected_objects
        return selected

    def get_current_measure(self):
        beat_timeline = globals_.TIMELINE_COLLECTION.find_by_class("BeatTimeline")
        if beat_timeline:
            measure = beat_timeline[0].find_previous_by_attr(
                "start", globals_.CURRENT_TIME, kind="measure"
            )
            if not measure:
                return None
            else:
                return measure.number
        else:
            return None
