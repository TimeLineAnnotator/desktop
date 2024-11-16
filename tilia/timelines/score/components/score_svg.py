from pathlib import Path

from tilia.timelines.base.component import SegmentLikeTimelineComponent
from tilia.timelines.base.validators import validate_time, validate_pre_validated
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.requests import get, Get


class ScoreSVG(SegmentLikeTimelineComponent):
    SERIALIZABLE_BY_VALUE = ["start", "end", "data"]
    ORDERING_ATTRS = ("start",)

    KIND = ComponentKind.SCORE_SVG

    def __init__(
        self,
        timeline: ScoreTimeline,
        id: int,
        start: float,
        end: float,
        data: str = "",
        **_,
    ):
        self.validators |= {
            "start": validate_time,
            "end": validate_time,
            "time": validate_time,
            "data": validate_pre_validated,
        }

        self.start = start
        self.end = end
        self._data = data

        super().__init__(timeline, id)

        self.svg_view = get(Get.TIMELINE_UI, self.timeline.id).svg_view
        self.svg_view.measure_box = self
        if data:
            self.svg_view.load_svg_data(self.data)

    @property
    def time(self) -> float:
        return (self.start + self.end) / 2

    @time.setter
    def time(self, value: float) -> None:
        self.svg_view.update_metric_position(
            (mp := get(Get.METRIC_POSITION, value)).measure,
            mp.beat / mp.measure_beat_count,
        )

    @property
    def data(self) -> str:
        return self._data

    @data.setter
    def data(self, data: str = "") -> None:
        self._data = data
        if data:
            self.svg_view.load_svg_data(self.data)

    def path_updated(self, path: Path) -> None:
        self.svg_view.get_svg(path)

    def save_data(self, data: str = ""):
        self._data = data
        self.update_hash()
