from __future__ import annotations

from typing import TYPE_CHECKING

from tilia.ui.timelines.base.element import TimelineUIElement

if TYPE_CHECKING:
    from tilia.ui.windows.score.score_view import ScoreView
    from tilia.ui.windows.svg_viewer import SvgViewer


class ScoreAnnotationUI(TimelineUIElement):
    UPDATE_TRIGGERS = ["x", "y", "viewer_id", "text", "font_size"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.get_data("text"):
            self._update_viewer()

    @property
    def svg_view(self) -> SvgViewer | ScoreView | None:
        return self.timeline_ui.svg_view

    def _update_viewer(self) -> None:
        # A timeline without a score has no viewer.
        if viewer := self.svg_view:
            viewer.update_annotation(self.id)

    def update_x(self):
        self._update_viewer()

    def update_y(self):
        self._update_viewer()

    def update_viewer_id(self):
        self._update_viewer()

    def update_text(self):
        self._update_viewer()

    def update_font_size(self):
        self._update_viewer()

    def delete(self):
        if viewer := self.svg_view:
            viewer.remove_annotation(self.id)
        return super().delete()

    def child_items(self):
        return []

    def on_select(self) -> None:
        pass

    def on_deselect(self) -> None:
        pass

    def update_position(self) -> None:
        pass
