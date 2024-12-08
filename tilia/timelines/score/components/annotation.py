from tilia.timelines.base.component import PointLikeTimelineComponent
from tilia.timelines.base.validators import (
    validate_pre_validated,
    validate_positive_integer,
    validate_string,
)
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.requests import get, Get
from tilia.ui.windows.svg_viewer import SvgViewer


class ScoreAnnotation(PointLikeTimelineComponent):
    SERIALIZABLE_BY_VALUE = ["x", "y", "viewer_id", "text", "font_size"]

    KIND = ComponentKind.SCORE_ANNOTATION

    def __init__(
        self,
        timeline: ScoreTimeline,
        id: int,
        x: float = 0,
        y: float = 0,
        viewer_id: int = 0,
        text: str = "",
        font_size: int = 12,
        **_,
    ):
        self.validators |= {
            "x": validate_pre_validated,
            "y": validate_pre_validated,
            "viewer_id": validate_pre_validated,
            "text": validate_string,
            "font_size": validate_positive_integer,
        }

        self._x = x
        self._y = y
        self._viewer_id = viewer_id
        self._text = text
        self._font_size = font_size

        super().__init__(timeline, id)

        self.svg_view: SvgViewer = get(Get.TIMELINE_UI, self.timeline.id).svg_view
        if text:
            self.svg_view.update_annotation(self)

    @property
    def x(self) -> float:
        return self._x

    @x.setter
    def x(self, x: float = 0) -> None:
        if self._x != x:
            self._x = x
            self.svg_view.update_annotation(self)

    @property
    def y(self) -> float:
        return self._y

    @y.setter
    def y(self, y: float = 0) -> None:
        if self._y != y:
            self._y = y
            self.svg_view.update_annotation(self)

    @property
    def viewer_id(self) -> int:
        return self._viewer_id

    @viewer_id.setter
    def viewer_id(self, viewer_id: int = 0) -> None:
        if self._viewer_id != viewer_id:
            self._viewer_id = viewer_id
            self.svg_view.update_annotation(self)

    @property
    def text(self) -> str:
        return self._text

    @text.setter
    def text(self, text: str = "") -> None:
        if self._text != text:
            self._text = text
            self.svg_view.update_annotation(self)

    @property
    def font_size(self) -> int:
        return self._font_size

    @font_size.setter
    def font_size(self, font_size: int = 12) -> None:
        if self._font_size != font_size:
            self._font_size = font_size
            self.svg_view.update_annotation(self)

    def remove_from_viewer(self):
        self.svg_view.remove_annotation(self)

    def save_data(
        self, x: float, y: float, viewer_id: int, text: str, font_size: int
    ) -> None:
        self._x = x
        self._y = y
        self._viewer_id = viewer_id
        self._text = text
        self._font_size = font_size
        self.update_hash()

    def get_viewer_data(self) -> dict:
        return {
            "x": self._x,
            "y": self._y,
            "viewer_id": self._viewer_id,
            "text": self._text,
            "font_size": self._font_size,
        }
