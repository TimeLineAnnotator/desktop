from __future__ import annotations
from typing import TYPE_CHECKING
from tilia.timelines.component_kinds import ComponentKind, get_component_class_by_kind

if TYPE_CHECKING:
    from tilia.timelines.base.component import TimelineComponent

import hashlib

from tilia.timelines.timeline_kinds import get_timeline_class_from_kind


def hash_function(string: str) -> str:
    return hashlib.md5(string.encode("utf-8")).hexdigest()
