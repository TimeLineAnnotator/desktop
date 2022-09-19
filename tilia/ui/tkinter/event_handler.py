import tkinter as tk
import tilia.events as events

from tilia.events import EventName
from tilia.ui.tkinter.modifier_enum import ModifierEnum


def on_mouse_wheel(event: tk.Event):
    if event.delta > 1:
        events.post(EventName.REQUEST_ZOOM_IN, event.widget.canvasx(event.x))
    elif event.delta < 1:
        events.post(EventName.REQUEST_ZOOM_OUT, event.widget.canvasx(event.x))


DEFAULT_CANVAS_BINDINGS = [
    ######################
    ### MOUSE BINDINGS ###
    ######################

    ("<ButtonPress-1>", lambda e: on_click(e, modifier=ModifierEnum.NONE)),
    (
        "<Shift-ButtonPress-1>",
        lambda e: on_click(e, modifier=ModifierEnum.SHIFT),
    ),
    (
        "<Control-ButtonPress-1>",
        lambda e: on_click(e, modifier=ModifierEnum.CONTROL),
    ),
    (
        "<Control-ButtonPress-1>",
        lambda e: on_click(e, modifier=ModifierEnum.CONTROL),
    ),
    (
        "<B1-Motion>",
        lambda e: events.post(
            EventName.TIMELINE_LEFT_BUTTON_DRAG,
            e.widget.canvasx(e.x),
            e.widget.canvasy(e.y),
        ),
    ),
    (
        "<ButtonRelease-1>",
        lambda _: events.post(EventName.TIMELINE_LEFT_BUTTON_RELEASE),
    ),
    ("<MouseWheel>", on_mouse_wheel),
    ("<Button-4>", on_mouse_wheel),
    ("<Button-5>", on_mouse_wheel),

    #########################
    ### KEYBOARD BINDINGS ###
    #########################

    (
        "<Control-D>",
        lambda _: events.post(EventName.DEBUG_SELECTED_ELEMENTS),
    ),
    ("<Delete>", lambda _: events.post(EventName.KEY_PRESS_DELETE)),
    ("<Return>", lambda _: events.post(EventName.KEY_PRESS_ENTER)),
    ("<Left>", lambda _: events.post(EventName.KEY_PRESS_LEFT)),
    ("<Right>", lambda _: events.post(EventName.KEY_PRESS_RIGHT)),
    (
        "<Control-i>",
        lambda _: events.post(EventName.UI_REQUEST_WINDOW_INSPECTOR),
    ),

    ("<Control-c>", lambda _: events.post(EventName.KEY_PRESS_CONTROL_C)),
    ("<Control-v>", lambda _: events.post(EventName.KEY_PRESS_CONTROL_V)),
    ("<Control-V>", lambda _: events.post(EventName.KEY_PRESS_CONTROL_SHIFT_V)),
    ("<Control-z>", lambda _: events.post(EventName.REQUEST_TO_UNDO)),
    ("<Control-y>", lambda _: events.post(EventName.REQUEST_TO_REDO)),
    ("<g>", lambda _: events.post(EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_GROUP)),
    ("<s>", lambda _: events.post(EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_SPLIT)),
    ("<M>", lambda _: events.post(EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_MERGE)),
    ("<Control-Up>", lambda _: events.post(EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_LEVEL_INCREASE)),
    ("<Control-Down>", lambda _: events.post(EventName.HIERARCHY_TOOLBAR_BUTTON_PRESS_LEVEL_DECREASE)),
    ("<space>", lambda _: events.post(EventName.PLAYER_REQUEST_TO_PLAYPAUSE))
]


class TkEventHandler:
    def __init__(self, root: tk.Tk):
        self.root = root
        self._make_default_canvas_bindings()

    def _make_default_canvas_bindings(self) -> None:
        for sequence, callback in DEFAULT_CANVAS_BINDINGS:
            self.root.bind_class("Canvas", sequence, callback)


def on_click(event: tk.Event, modifier: ModifierEnum):
    """Handles mouse click"""
    canvas = event.widget
    canvas_x = canvas.canvasx(event.x)
    canvas_y = canvas.canvasx(event.y)
    clicked_item_id = next(iter(canvas.find_withtag(tk.CURRENT)), None)

    events.post(
        EventName.CANVAS_LEFT_CLICK,
        canvas,
        canvas_x,
        canvas_y,
        clicked_item_id,
        modifier=modifier,
    )
