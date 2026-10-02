from tilia.ui.coords import time_x_converter
from tilia.ui.timelines.score.element.with_collision import (
    TimelineUIElementWithCollision,
)
from tilia.ui.timelines.time_signature_glyphs import TimeSignatureBody


class TimeSignatureUI(TimelineUIElementWithCollision):
    MARGIN_X = 2
    MARGIN_Y = 10
    MAX_PIXMAP_HEIGHT = 12

    def __init__(self, *args, **kwargs):
        super().__init__(self.MARGIN_X, *args, **kwargs)
        self._setup_body()

    @property
    def x(self):
        return time_x_converter.get_x_by_time(self.get_data("time"))

    def body_y(self):
        return (
            self.MARGIN_Y * self.timeline_ui.get_scale_for_symbols_above_staff()
            + self.timeline_ui.get_y_for_symbols_above_staff(
                self.get_data("staff_index")
            )
        )

    def _setup_body(self):
        self.body = TimeSignatureBody(
            self.x,
            self.body_y(),
            self.get_data("numerator"),
            self.get_data("denominator"),
            self.get_body_digit_height(),
            self.timeline_ui.pixmaps["time signature"],
        )
        self.body.moveBy(self.x_offset, 0)
        self.scene.addItem(self.body)

    def get_body_digit_height(self) -> int:
        return min(
            self.MAX_PIXMAP_HEIGHT,
            int(
                (self.timeline_ui.get_height_for_symbols_above_staff() - self.MARGIN_Y)
                / 2
            ),
        )

    def child_items(self):
        return [self.body]

    def update_position(self):
        self.body.set_position(
            self.x
            + self.x_offset
            + (self.margin_x if self.x_offset is not None else 0),
            self.body_y(),
        )
        self.body.set_height(self.get_body_digit_height())

    def on_components_deserialized(self):
        self.update_position()

    def selection_triggers(self):
        return []

    def on_deselect(self):
        return

    def on_select(self):
        return
