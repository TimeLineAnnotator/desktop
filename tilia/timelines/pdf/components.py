from __future__ import annotations

from typing import TYPE_CHECKING

from tilia.timelines.base.validators import (
    validate_time,
    validate_positive_integer,
)
from tilia.timelines.component_kinds import ComponentKind

if TYPE_CHECKING:
    from tilia.timelines.pdf.timeline import PdfTimeline

from tilia.timelines.base.component import PointLikeTimelineComponent


class PdfMarker(PointLikeTimelineComponent):
    SERIALIZABLE_BY_VALUE = ["time", "page_number"]
    SERIALIZABLE_BY_ID = []
    SERIALIZABLE_BY_ID_LIST = []
    ORDERING_ATTRS = ("time",)

    KIND = ComponentKind.PDF_MARKER

    validators = {
        "timeline": lambda _: False,
        "id": lambda _: False,
        "time": validate_time,
        "page_number": validate_positive_integer,
    }

    def __init__(
        self,
        timeline: PdfTimeline,
        id: int,
        time: float,
        page_number: int,
        **_,
    ):
        super().__init__(timeline, id)

        self.time = time
        self.page_number = page_number

    def __str__(self):
        return f"PdfMarker({self.time})"

    def __repr__(self):
        return str(dict(self.__dict__.items()))

    @property
    def frontend_name(self):
        return "page marker"
