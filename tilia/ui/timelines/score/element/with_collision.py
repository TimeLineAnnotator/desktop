from tilia.ui.coords import time_x_converter
from tilia.ui.timelines.base.element import TimelineUIElement


class TimelineUIElementWithCollision(TimelineUIElement):
    def __init__(self, margin_x, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.margin_x = margin_x
        self._x_offset = None

    @property
    def width(self):
        return self.body.boundingRect().width() + self.margin_x * 2

    @property
    def x(self):
        return time_x_converter.get_x_by_time(self.get_data('time'))

    @property
    def x_offset(self):
        return - self.width / 2 if self._x_offset is None else self._x_offset

    @x_offset.setter
    def x_offset(self, value):
        self._x_offset = value
        self.update_position()
