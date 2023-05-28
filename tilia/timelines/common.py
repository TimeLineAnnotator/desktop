"""
Classes and functions common to most timelines.
Contains the following interfaces, that should be implemented by specific timelines:
    - Timeline
    - TimelineComponentManager
    - TimelineComponent
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from typing import Callable
import logging

logger = logging.getLogger(__name__)


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
