from __future__ import annotations

from typing import Any, Callable

from tilia.exceptions import SetComponentDataError, GetComponentDataError
from tilia.timelines.base.timeline import Timeline
from tilia.timelines.base.validators import validate_read_only
from tilia.timelines.hash_timelines import hash_function
from tilia.utils import get_tilia_class_string


class TimelineComponent:
    SERIALIZABLE = []
    ORDERING_ATTRS = tuple()

    validators = {
        "timeline": validate_read_only,
        "id": validate_read_only,
    }

    def __init__(self, timeline: Timeline, id: int, *args, **kwargs):
        self.timeline = timeline
        self.id = id
        self.update_hash()

    def __str__(self):
        return get_tilia_class_string(self)

    def __lt__(self, other):
        return self.ordinal < other.ordinal

    @classmethod
    def frontend_name(cls):
        return cls.__name__.lower()

    @property
    def ordinal(self):
        return tuple(getattr(self, attr) for attr in self.ORDERING_ATTRS)

    def to_hash(self):
        string_to_hash = ""
        for attr in self.SERIALIZABLE:
            string_to_hash += "|" + str(getattr(self, attr))
        return hash_function(string_to_hash)

    def update_hash(self):
        self.hash = self.to_hash()

    def validate_set_data(self, attr, value):
        if not hasattr(self, attr):
            raise SetComponentDataError(
                f"Component '{self}' has no attribute named '{attr}'. Can't set to '{value}'."
            )
        try:
            return self.validators[attr](value)
        except KeyError as e:
            raise KeyError(
                f"{self} has no validator for attribute {attr}. Can't set to '{value}'."
            ) from e

    def set_data(self, attr: str, value: Any):
        if not self.validate_set_data(attr, value):
            return None, False
        setattr(self, attr, value)
        if attr in self.ORDERING_ATTRS:
            self.timeline.update_component_order(self)
        self.update_hash()
        return value, True

    def get_data(self, attr: str):
        try:
            return getattr(self, attr)
        except AttributeError as e:
            raise GetComponentDataError(
                "AttributeError while getting data from component."
                f"Does {type(self)} have a {attr} attribute?"
            ) from e

    @classmethod
    def validate_creation(cls, *args, **kwargs) -> tuple[bool, str]:
        return True, ""

    @staticmethod
    def compose_validators(
        validators: list[Callable[[], tuple[bool, str]]],
    ) -> tuple[bool, str]:
        """Calls validators in order and returns (False, reason) if any fails. Returns (True, '') if all succeed."""
        for validator in validators:
            success, reason = validator()
            if not success:
                return False, reason
        return True, ""
