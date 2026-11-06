from __future__ import annotations

from tilia.timelines.base.component import TimelineComponent
from tilia.timelines.base.validators import (
    validate_color,
    validate_pre_validated,
    validate_string,
)
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.pcset import PitchClassSetAnalysis
from tilia.timelines.score.timeline import ScoreTimeline


class NoteGroup(TimelineComponent):
    """Notes of the score an analyst has grouped. Notes are named by their
    elements in the score, since a repeated measure's one element has a note
    component for each time it's played."""

    SERIALIZABLE = ["element_ids", "label", "color"]
    ORDERING_ATTRS = ("_order",)

    KIND = ComponentKind.NOTE_GROUP

    validators = {
        "timeline": lambda _: False,
        "id": lambda _: False,
        "element_ids": validate_pre_validated,
        "label": validate_string,
        "color": validate_color,
    }

    def __init__(
        self,
        timeline: ScoreTimeline,
        id: int,
        element_ids: list[str],
        label: str = "",
        color: str | None = None,
        **_,
    ):
        self.element_ids = list(element_ids)
        self.label = label
        self.color = color
        # Components of all kinds share one order, and times aren't negative.
        self._order = -1.0

        super().__init__(timeline, id)

    @property
    def analysis(self) -> PitchClassSetAnalysis:
        return self.timeline.analyse_elements(self.element_ids)
