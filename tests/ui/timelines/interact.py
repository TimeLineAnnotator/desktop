from PyQt6.QtCore import Qt

from tilia.requests import Post, post
from tilia.ui.coords import get_time_by_x


def click_timeline_ui_view(view, button, x, y, item, modifier, double):
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


def click_timeline_ui(timeline_ui, time, button="left", modifier=None, double=False):
    (
        x,
        y,
    ) = int(
        get_time_by_x(time)
    ), int(timeline_ui.get_data("height") / 2)
    item = timeline_ui.view.itemAt(x, y)
    click_timeline_ui_view(timeline_ui.view, button, x, y, item, modifier, double)


def drag_mouse_in_timeline_view(x, y):
    post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, int(x), int(y))
