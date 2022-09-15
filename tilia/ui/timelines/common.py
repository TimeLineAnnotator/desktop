from __future__ import annotations
from typing import TYPE_CHECKING

from tilia.timelines.timeline_kinds import TimelineKind

if TYPE_CHECKING:
    from tilia.timelines.common import TimelineComponent

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class TimelineComponentUI:
    pass


class TimelineUICollection(ABC):
    """
    Interface for TimelineUI.
    Not not up to date as to what methods are needed."""

    @abstractmethod
    def create_timeline_ui(self, timeline_kind: TimelineKind, name: str) -> TimelineUI:
        ...

    @abstractmethod
    def get_id(self) -> str:
        ...


class TimelineUI:
    def __init__(
        self,
        *args,
        timeline_ui_collection: TimelineUICollection,
        height: int,
        is_visible: bool,
        name: str,
        **kwargs,
    ):
        super(TimelineUI, self).__init__(*args, **kwargs)

        self.timeline_ui_collection = timeline_ui_collection
        self.height = height
        self.visible = is_visible
        self.name = name

        self._timeline = None

    @property
    def timeline(self):
        return self._timeline

    @timeline.setter
    def timeline(self, value):
        logger.debug(f"Setting {self} timeline as {value}")
        self._timeline = value

    def get_id(self) -> str:
        return self.timeline_ui_collection.get_id()


class TimelineUIElement(ABC):
    def __init__(
        self, *args, tl_component: TimelineComponent, timeline_ui: TimelineUI, **kwargs
    ):
        super().__init__(*args, **kwargs)

        self.tl_component = tl_component
        self.timeline_ui = timeline_ui
        self.id = timeline_ui.get_id()

    @abstractmethod
    def update_position(self) -> None: ...

    @property
    @abstractmethod
    def canvas_drawings_ids(self) -> tuple[int]: ...

