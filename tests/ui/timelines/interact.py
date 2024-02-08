from PyQt6.QtCore import Qt

from tilia.requests import Post, post


def click_timeline_ui_view(view, button, x, y, item, modifier, double):
    request = {
        "left": Post.TIMELINE_VIEW_LEFT_CLICK,
        "right": Post.TIMELINE_VIEW_RIGHT_CLICK,
    }[button]

    modifier = {None: Qt.KeyboardModifier.NoModifier}[modifier]

    post(
        request,
        view,
        x,
        y,
        item,
        modifier,
        double=double,
    )


def drag_mouse_in_timeline_view(x, y):
    post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, int(x), int(y))
