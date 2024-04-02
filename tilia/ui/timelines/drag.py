from typing import Callable

from tilia.requests import listen, Post, stop_listening


def noop(*_, **__):
    pass


class DragManager:
    def __init__(
        self,
        get_min_x: Callable,
        get_max_x: Callable,
        before_each=noop,
        after_each=noop,
        on_release=noop,
    ):
        self.get_min_x = get_min_x
        self.get_max_x = get_max_x
        self.before_each = before_each
        self.after_each = after_each
        self.on_release = on_release

        listen(self, Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, self.on_mouse_drag)
        listen(self, Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE, self.on_mouse_release)

    def on_mouse_drag(self, x: int, _: int):  # ignores the y coordinate
        self.before_each()
        dragged_to = minmax(x, self.get_min_x(), self.get_max_x())
        self.after_each(dragged_to)

    def on_mouse_release(self):
        stop_listening(self, Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG)
        stop_listening(self, Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)
        self.on_release()


def minmax(x: int, min_x: int, max_x: int) -> int:
    result = x
    if x > max_x:
        result = max_x
    elif x < min_x:
        result = min_x

    return result
