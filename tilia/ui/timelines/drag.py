import logging
from typing import Callable

from tilia.requests import listen, Post, stop_listening

logger = logging.getLogger(__name__)


def noop(*args, **kwargs):
    pass


class DragManager:
    def __init__(self, get_min_x: Callable, get_max_x: Callable, before_each=noop, after_each=noop, on_release=noop):
        self.get_min_x = get_min_x
        self.get_max_x = get_max_x
        self.before_each = before_each
        self.after_each = after_each
        self.on_release = on_release

        listen(self, Post.TIMELINE_LEFT_BUTTON_DRAG, self.on_mouse_drag)
        listen(self, Post.TIMELINE_LEFT_BUTTON_RELEASE, self.on_mouse_release)

    def on_mouse_drag(self, x: int, _: int):  # ignores the y coordinate
        self.before_each()
        dragged_to = self.drag(x, self.get_min_x(), self.get_max_x())
        self.after_each(dragged_to)
        
    def on_mouse_release(self):
        stop_listening(self, Post.TIMELINE_LEFT_BUTTON_DRAG)
        stop_listening(self, Post.TIMELINE_LEFT_BUTTON_RELEASE)
        self.on_release()
        
    @staticmethod
    def drag(x: int, min_x: int, max_x: int) -> int:
        logger.debug(f"Dragging...")
        dragged_to = x
        if x > max_x:
            logger.debug(
                f"Mouse is beyond right drag limit. Dragging to max x='{max_x}'"
            )
            dragged_to = max_x
        elif x < min_x:
            logger.debug(
                f"Mouse is beyond left drag limit. Dragging to min x='{min_x}'"
            )
            dragged_to = min_x

        logger.debug(f"Dragging to x='{dragged_to}'.")
        return dragged_to
