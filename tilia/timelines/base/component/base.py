from __future__ import annotations

from abc import ABC
from typing import Any, Callable

from tilia.exceptions import SetComponentDataError, GetComponentDataError
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.base.validators import validate_read_only
from tilia.utils import get_tilia_class_string


class TimelineComponent(ABC):
    SERIALIZABLE_BY_VALUE = []
    SERIALIZABLE_BY_ID = []
    SERIALIZABLE_BY_ID_LIST = []
    ORDERING_ATTRS = tuple()

    validators = {
        "timeline": validate_read_only,
        "id": validate_read_only,
    }

    def __init__(self, timeline: Timeline, id: int, *args, **kwargs):
        self.timeline = timeline
        self.id = id

    def __str__(self):
        return get_tilia_class_string(self)

    def __lt__(self, other):
        return self.ordinal < other.ordinal

    @property
    def frontend_name(self):
        return self.__class__.__name__.lower()

    @property
    def ordinal(self):
        return tuple(getattr(self, attr) for attr in self.ORDERING_ATTRS)

    def validate_set_data(self, attr, value):
        if not hasattr(self, attr):
            raise SetComponentDataError(
                f"Component '{self}' has no attribute named '{attr}'. Can't set to '{value}'."
            )
        try:
            return self.validators[attr](value)
        except KeyError:
            raise KeyError(
                f"{self} has no validator for attribute {attr}. Can't set to '{value}'."
            )

    def set_data(self, attr: str, value: Any):
        if not self.validate_set_data(attr, value):
            return None, False
        setattr(self, attr, value)
        if attr in self.ORDERING_ATTRS:
            self.timeline.update_component_order(self)
        return value, True

    def validate_get_data(self, attr):
        if not hasattr(self, attr):
            raise GetComponentDataError(
                f"Component '{self}' has no attribute named '{attr}'"
            )
        return True

    def get_data(self, attr: str):
        if self.validate_get_data(attr):
            return getattr(self, attr)

    @classmethod
    def validate_creation(cls, *args, **kwargs) -> tuple[bool, str]:
        return True, ""

    @staticmethod
    def compose_validators(validators: list[Callable[[], tuple[bool, str]]]) -> tuple[bool, str]:
        """Calls validators in order and returns (False, reason) if any fails. Returns (True, '') if all succeed."""
        for validator in validators:
            success, reason = validator()
            if not success:
                return False, reason
        return True, ''
