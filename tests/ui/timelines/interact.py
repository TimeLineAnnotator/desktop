from typing import Literal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsView, QGraphicsItem, QApplication
from PySide6.QtTest import QTest

from tilia.requests import Post, post, get, Get
from tilia.ui.coords import time_x_converter
from tilia.ui.timelines.base.element import TimelineUIElement


def click_timeline_ui_view(
    view: QGraphicsView,
    button: Literal["left", "right", "middle"],
    x: float,
    y: float,
    item: QGraphicsItem | None = None,
    modifier: Literal["alt", "ctrl", "shift"]
    | list[Literal["alt", "ctrl", "shift"]]
    | None = None,
    double: bool = False,
):
    request = {
        "left": Post.TIMELINE_VIEW_LEFT_CLICK,
        "right": Post.TIMELINE_VIEW_RIGHT_CLICK,
    }[button]

    if not isinstance(modifier, list):
        modifier = [modifier]

    modifier_map = {
        None: Qt.KeyboardModifier.NoModifier,
        "shift": Qt.KeyboardModifier.ShiftModifier,
        "ctrl": Qt.KeyboardModifier.ControlModifier,
        "alt": Qt.KeyboardModifier.AltModifier,
    }

    modifiers = modifier_map[modifier[0]]
    for m in modifier[1:]:
        modifiers |= modifier_map[m]

    post(
        request,
        view,
        x,
        y,
        item,
        modifiers,
        double=double,
    )


def click_timeline_ui(
    timeline_ui, time, y=None, button="left", modifier=None, double=False
):
    x = int(time_x_converter.get_x_by_time(time))
    y = int(y or timeline_ui.get_data("height") / 2)
    item = timeline_ui.view.itemAt(x, y)
    click_timeline_ui_view(timeline_ui.view, button, x, y, item, modifier, double)


def click_timeline_ui_element_body(
    item: TimelineUIElement,
    button: Literal["left", "right", "middle"] = "left",
    modifier: Literal["alt", "ctrl", "shift"]
    | list[Literal["alt", "ctrl", "shift"]]
    | None = None,
    double: bool = False,
):
    to_click = item.body
    x = to_click.pos().x()
    y = to_click.pos().y()
    click_timeline_ui_view(
        item.timeline_ui.view, button, x, y, to_click, modifier, double
    )


def drag_mouse_in_timeline_view(x, y, release=True):
    # assumes timeline view has already been clicked
    post(Post.TIMELINE_VIEW_LEFT_BUTTON_DRAG, int(x), int(y))
    if release:
        post(Post.TIMELINE_VIEW_LEFT_BUTTON_RELEASE)


def get_focused_widget():
    get(Get.MAIN_WINDOW).show()
    QApplication.processEvents()
    return QApplication.focusWidget()


def press_key(key: str, modifier: Qt.KeyboardModifier | None = None):
    if len(key) > 1:
        try:
            key = getattr(Qt.Key, f"Key_{key}")
        except AttributeError:
            raise ValueError(f"Unknown key: {key}")

    QTest.keyClick(
        get_focused_widget(), key, modifier=modifier or Qt.KeyboardModifier.NoModifier
    )


def type_string(text: str):
    QTest.keyClicks(get_focused_widget(), text)
