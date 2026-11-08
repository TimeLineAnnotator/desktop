from __future__ import annotations

from tilia.settings import settings
from tilia.timelines.base.timeline import Timeline, TimelineFlag


class SetsTimeline(Timeline):
    """A lane with the score timelines' note groups. It holds nothing of its
    own: the groups belong to their score, so there's nothing to edit here."""

    FLAGS = [
        TimelineFlag.COMPONENTS_NOT_EDITABLE,
        TimelineFlag.NOT_CLEARABLE,
        TimelineFlag.NOT_DUPLICATABLE,
        TimelineFlag.NOT_EXPORTABLE,
    ]

    @property
    def default_height(self) -> int:
        return settings.get("sets_timeline", "row_height")

    @property
    def components(self) -> list:
        return []

    def get_state(self) -> dict:
        return self._get_base_state() | {"components": {}, "components_hash": ""}

    def deserialize_components(self, components: dict[int, dict[str]]) -> None:
        """Nothing to do."""

    def clear(self) -> None:
        """Nothing to do."""

    def delete(self) -> None:
        """Nothing to do."""

    def crop(self, length: float) -> None:
        """Nothing to do."""

    def scale(self, factor: float) -> None:
        """Nothing to do."""
