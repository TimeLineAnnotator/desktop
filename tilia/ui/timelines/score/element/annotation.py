from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.windows.svg_viewer import SvgViewer


class ScoreAnnotationUI(TimelineUIElement):
    UPDATE_TRIGGERS = ["x", "y", "viewer_id", "text", "font_size"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.get_data("text"):
            self.svg_view.update_annotation(self.id)

    @property
    def svg_view(self) -> SvgViewer:
        return self.timeline_ui.svg_view

    def update_x(self):
        self.svg_view.update_annotation(self.id)

    def update_y(self):
        self.svg_view.update_annotation(self.id)

    def update_viewer_id(self):
        self.svg_view.update_annotation(self.id)

    def update_text(self):
        self.svg_view.update_annotation(self.id)

    def update_font_size(self):
        self.svg_view.update_annotation(self.id)

    def delete(self):
        self.svg_view.remove_annotation(self.id)
        return super().delete()

    def child_items(self):
        return []

    def on_select(self) -> None:
        pass

    def on_deselect(self) -> None:
        pass

    def update_position(self) -> None:
        pass
