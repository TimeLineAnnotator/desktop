from pathlib import Path

from tilia.timelines.base.component import SegmentLikeTimelineComponent
from tilia.timelines.base.validators import validate_time
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.requests import get, Get
from tilia.ui.windows.svg_viewer import SvgViewer


class ScoreViewer(SegmentLikeTimelineComponent):
    SERIALIZABLE_BY_VALUE = ["start", "end"]
    ORDERING_ATTRS = ("start",)

    KIND = ComponentKind.SCORE_VIEWER

    def __init__(
        self,
        timeline: ScoreTimeline,
        id: int,
        start: float,
        end: float,
        **_,
    ):
        self.validators |= {
            "start": validate_time,
            "end": validate_time,
            "time": validate_time,
        }

        self.start = start
        self.end = end

        super().__init__(timeline, id)

        self.svg_view: SvgViewer = get(Get.TIMELINE_UI, self.timeline.id).svg_view
        self.svg_view.measure_box = self

    @property
    def time(self) -> float:
        return (self.start + self.end) / 2

    @time.setter
    def time(self, value: float) -> None:
        self.svg_view.update_metric_position(
            (mp := get(Get.METRIC_POSITION, value)).measure,
            mp.beat / mp.measure_beat_count,
        )
