"""
Classes and functions common to most timelines.
Contains the following interfaces, that should be implemented by specific timelines:
    - Timeline
    - TimelineComponentManager
    - TimelineComponent
"""

from __future__ import annotations
from typing import TYPE_CHECKING

import tilia.repr
import tilia.timelines.serialize

if TYPE_CHECKING:
    from .base.timeline import Timeline

from typing import Callable
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class InvalidComponentKindError(Exception):
    pass


class TimelineComponent(ABC):
    """Interface for objects that compose a timeline. E.g. the Hierarchy class
    in HierarchyTimelines."""

    def __init__(self, timeline: Timeline):
        self.timeline = timeline
        self.id = timeline.get_id_for_component()
        self.ui = None

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


def log_object_creation(func: Callable) -> Callable:
    """Wraps an object's __init__ method to log a "Starting x creation..."
    message after method call and a "Created x." message after method call.
    Where x is the object's __repr__."""

    def wrapper(self, *args, **kwargs):
        logger.debug(f"Creating {self.__class__.__name__} with {args=}, {kwargs=}...")
        result = func(self, *args, **kwargs)
        logger.debug(f"Created {self.__class__.__name__}.")
        return result

    return wrapper


def log_object_deletion(func: Callable) -> Callable:
    """Wraps an object's delete or destroy method to log a "Starting x deletion..."
    message after method call and a "Deleted x." message after method call.
    Where x is the object's __repr__."""

    def wrapper(self, *args, **kwargs):
        logger.debug(f"Deleting {self.__class__.__name__}...")
        result = func(self, *args, **kwargs)
        logger.debug(f"Deleted {self.__class__.__name__}.")
        return result

    return wrapper
