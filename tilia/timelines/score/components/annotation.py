from tilia.timelines.base.component import PointLikeTimelineComponent
from tilia.timelines.base.validators import validate_pre_validated
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.requests import get, Get
from tilia.ui.windows.svg_viewer import SvgViewer


class ScoreAnnotation(PointLikeTimelineComponent):
    SERIALIZABLE_BY_VALUE = ["data"]

    KIND = ComponentKind.SCORE_ANNOTATION

    def __init__(
        self,
        timeline: ScoreTimeline,
        id: int,
        data: str = "",
        **_,
    ):
        self.validators |= {
            "data": validate_pre_validated,
        }

        self._data = data

        super().__init__(timeline, id)

        self.svg_view: SvgViewer = get(Get.TIMELINE_UI, self.timeline.id).svg_view
        if data:
            self.svg_view.update_annotation(data, self)

    @property
    def data(self) -> str:
        return self._data

    @data.setter
    def data(self, data: str = "") -> None:
        self._data = data
        if data:
            self.svg_view.update_annotation(data, self)

    def save_data(self, data: str = ""):
        self._data = data
        self.update_hash()
