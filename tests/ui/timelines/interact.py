from typing import Literal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGraphicsView, QGraphicsItem, QApplication

from tilia.requests import Post, post
from tilia.ui.coords import time_x_converter


def click_timeline_ui_view(
    view: QGraphicsView,
    button: Literal["left", "right", "middle"],
    x: float,
    y: float,
    item: QGraphicsItem | None = None,
    modifier: Literal["shift", "control"] | None = None,
    double: bool = False,
):
    request = {
        "left": Post.TIMELINE_VIEW_LEFT_CLICK,
        "right": Post.TIMELINE_VIEW_RIGHT_CLICK,
    }[button]

    modifier = {
        None: Qt.KeyboardModifier.NoModifier,
        "shift": Qt.KeyboardModifier.ShiftModifier,
    }[modifier]

    post(
        request,
        view,
        x,
        y,
        item,
        modifier,
        double=double,
    )


def click_timeline_ui(
    timeline_ui, time, y=None, button="left", modifier=None, double=False
):
    x = int(time_x_converter.get_x_by_time(time))
    y = int(y or timeline_ui.get_data("height") / 2)
    item = timeline_ui.view.itemAt(x, y)
    click_timeline_ui_view(timeline_ui.view, button, x, y, item, modifier, double)


def drag_mouse_in_timeline_view(x, y):
    # assumes timeline view has already been clicked
    post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, int(x), int(y))
