from __future__ import annotations

from abc import ABC, abstractmethod

import tilia.repr
from tilia.timelines.base.timeline import Timeline


class TimelineComponent(ABC):
    """Interface for objects that compose a timeline. E.g. the Hierarchy class
    in HierarchyTimelines."""

    def __init__(self, timeline: Timeline):
        self.timeline = timeline
        self.id = timeline.get_id_for_component()

    @classmethod
    @abstractmethod
    def create(cls, *args, **kwargs):
        """Should call the constructor of the appropriate subclass."""

    @abstractmethod
    def receive_delete_request_from_ui(self) -> None:
        """Calls own delete method and ui's delete method.
        May validate delete request prior to performing
        deletion."""

    def __str__(self):
        return tilia.repr.default_str(self)
