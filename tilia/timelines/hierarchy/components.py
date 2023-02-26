"""
Defines the Hierarchy class, the single TimelineComponent kind of a HierarchyTimeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tilia.timelines.component_kinds import ComponentKind
from tilia.misc_enums import StartOrEnd

if TYPE_CHECKING:
    from tilia.timelines.hierarchy.timeline import HierarchyTimeline

import tkinter as tk

from tilia.exceptions import AppException

from tilia.timelines.common import (
    TimelineComponent,
)

import logging

logger = logging.getLogger(__name__)


class HierarchyLoadError(Exception):
    pass


class Hierarchy(TimelineComponent):

    # serializer attributes
    SERIALIZABLE_BY_VALUE = [
        "start",
        "pre_start",
        "end",
        "post_end",
        "level",
        "formal_type",
        "formal_function",
        "comments",
    ]

    SERIALIZABLE_BY_UI_VALUE = ["label", "color"]
    SERIALIZABLE_BY_ID = ["parent"]
    SERIALIZABLE_BY_ID_LIST = ["children"]

    KIND = ComponentKind.HIERARCHY

    def __init__(
        self,
        timeline: HierarchyTimeline,
        start: float,
        end: float,
        level: int,
        parent=None,
        children=None,
        comments="",
        pre_start=None,
        post_end=None,
        formal_type="",
        formal_function="",
        **_,
    ):

        super().__init__(timeline)

        self._start = start
        self._end = end
        self.level = level
        self.comments = comments

        self.formal_type = formal_type
        self.formal_function = formal_function

        self.parent = parent

        self.children = children if children else []
        self.pre_start = pre_start if pre_start else self.start
        self.post_end = post_end if post_end else self.end

        self.ui = None

    @classmethod
    def create(
        cls,
        timeline: HierarchyTimeline,
        start: float,
        end: float,
        level: int,
        parent=None,
        children=None,
        comments="",
        pre_start=None,
        post_end=None,
        formal_type="",
        formal_function="",
        **kwargs,
    ):
        return Hierarchy(
            timeline,
            start,
            end,
            level,
            parent,
            children,
            comments,
            pre_start,
            post_end,
            formal_type,
            formal_function,
            **kwargs,
        )

    def receive_delete_request_from_ui(self) -> None:
        self.timeline.on_request_to_delete_components([self])
        self.ui.delete()

    @property
    def start(self):
        return self._start

    @start.setter
    def start(self, value):
        logger.debug(f"Setting {self} start to {value}")
        prev_start = self._start
        self._start = value
        if self.pre_start > value or self.pre_start == prev_start:
            self.pre_start = value

    @property
    def end(self):
        return self._end

    @end.setter
    def end(self, value):
        logger.debug(f"Setting {self} end to {value}")
        prev_end = self._end
        self._end = value
        if self.post_end < value or self.post_end == prev_end:
            self.post_end = value

    def __repr__(self):
        repr_ = f"Hierarchy({self.start}, {self.end}, {self.level}"
        try:
            if self.ui.label:
                repr_ += f", {self.ui.label}"
        except AttributeError:
            pass  # UI has not been created yet
        repr_ += ")"
        return repr_


class HierarchyOperationError(AppException):
    pass
