import sys
import tkinter as tk
import tilia.events as events
from tilia import globals_

from tilia.events import Event
from tilia.ui.canvas_tags import CLICK_THROUGH
from tilia.ui.modifier_enum import ModifierEnum


def on_mouse_wheel(event: tk.Event):
    if sys.platform == "darwin":
        event.delta *= -1

    if event.delta > 0:
        events.post(Event.REQUEST_ZOOM_IN)
    elif event.delta < 0:
        events.post(Event.REQUEST_ZOOM_OUT)


if sys.platform == "win32" or "linux":
    right_click_keysym = "<ButtonPress-3>"
else:
    right_click_keysym = "<ButtonPress-2>"

DEFAULT_CANVAS_BINDINGS = [
    ######################
    ### MOUSE BINDINGS ###
    ######################
    (
        "<ButtonPress-1>",
        lambda e: on_left_click(e, modifier=ModifierEnum.NONE, double=False),
    ),
    (
        "<Shift-ButtonPress-1>",
        lambda e: on_left_click(e, modifier=ModifierEnum.SHIFT, double=False),
    ),
    (
        "<Control-ButtonPress-1>",
        lambda e: on_left_click(e, modifier=ModifierEnum.CONTROL, double=False),
    ),
    (
        "<Control-ButtonPress-1>",
        lambda e: on_left_click(e, modifier=ModifierEnum.CONTROL, double=False),
    ),
    (
        "<B1-Motion>",
        lambda e: events.post(
            Event.TIMELINE_LEFT_BUTTON_DRAG,
            e.widget.canvasx(e.x),
            e.widget.canvasy(e.y),
            logging_level=5,
        ),
    ),
    (
        "<ButtonRelease-1>",
        lambda _: events.post(Event.TIMELINE_LEFT_BUTTON_RELEASE),
    ),
    (
        "<Double-Button-1>",
        lambda e: on_left_click(e, modifier=ModifierEnum.NONE, double=True),
    ),
    (
        right_click_keysym,
        lambda e: on_right_click(e, modifier=ModifierEnum.NONE, double=False),
    ),
    ("<MouseWheel>", on_mouse_wheel),
    ("<Button-4>", lambda: events.post(Event.REQUEST_ZOOM_IN)),
    ("<Button-5>", lambda: events.post(Event.REQUEST_ZOOM_OUT)),
    #########################
    ### KEYBOARD BINDINGS ###
    #########################
    (
        "<Control-D>",
        lambda _: events.post(Event.DEBUG_SELECTED_ELEMENTS),
    ),
    ("<Delete>", lambda _: events.post(Event.KEY_PRESS_DELETE)),
    ("<Return>", lambda _: events.post(Event.KEY_PRESS_ENTER)),
    ("<Left>", lambda _: events.post(Event.KEY_PRESS_LEFT)),
    ("<Right>", lambda _: events.post(Event.KEY_PRESS_RIGHT)),
    ("<Up>", lambda _: events.post(Event.KEY_PRESS_UP)),
    ("<Down>", lambda _: events.post(Event.KEY_PRESS_DOWN)),
    (
        "<Control-i>",
        lambda _: events.post(Event.UI_REQUEST_WINDOW_INSPECTOR),
    ),
    ("<Control-c>", lambda _: events.post(Event.KEY_PRESS_CONTROL_C)),
    ("<Control-v>", lambda _: events.post(Event.KEY_PRESS_CONTROL_V)),
    ("<Control-V>", lambda _: events.post(Event.KEY_PRESS_CONTROL_SHIFT_V)),
    ("<Control-z>", lambda _: events.post(Event.REQUEST_TO_UNDO)),
    ("<Control-y>", lambda _: events.post(Event.REQUEST_TO_REDO)),
    ("<Control-s>", lambda _: events.post(Event.FILE_REQUEST_TO_SAVE, save_as=False)),
    ("<Control-S>", lambda _: events.post(Event.FILE_REQUEST_TO_SAVE, save_as=True)),
    ("<Control-S>", lambda _: events.post(Event.FILE_REQUEST_TO_SAVE, save_as=True)),
    ("<Control-S>", lambda _: events.post(Event.FILE_REQUEST_TO_SAVE, save_as=True)),
    ("<Control-plus>", lambda _: events.post(Event.REQUEST_ZOOM_IN)),
    ("<Control-minus>", lambda _: events.post(Event.REQUEST_ZOOM_OUT)),
    ("<g>", lambda _: events.post(Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_GROUP)),
    ("<s>", lambda _: events.post(Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_SPLIT)),
    ("<M>", lambda _: events.post(Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_MERGE)),
    (
        "<Control-Up>",
        lambda _: events.post(Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_LEVEL_INCREASE),
    ),
    (
        "<Control-Down>",
        lambda _: events.post(Event.HIERARCHY_TOOLBAR_BUTTON_PRESS_LEVEL_DECREASE),
    ),
    ("<m>", lambda _: events.post(Event.MARKER_TOOLBAR_BUTTON_ADD)),
    ("<b>", lambda _: events.post(Event.BEAT_TOOLBAR_BUTTON_ADD)),
    ("<space>", lambda _: events.post(Event.PLAYER_REQUEST_TO_PLAYPAUSE)),
]


def get_highest_in_stacking_order(ids: set, canvas: tk.Canvas) -> int:
    ids_in_order = [id_ for id_ in canvas.find_all() if id_ in ids]
    return ids_in_order[-1]


def on_left_click(event: tk.Event, modifier: ModifierEnum, double: bool):
    """Handles mouse click"""
    canvas = event.widget
    canvas_x = canvas.canvasx(event.x)
    canvas_y = canvas.canvasy(event.y)
    clicked_item_id = next(iter(canvas.find_withtag(tk.CURRENT)), None)

    if clicked_item_id and CLICK_THROUGH in canvas.gettags(clicked_item_id):
        overlapping = set(
            canvas.find_overlapping(canvas_x, canvas_y, canvas_x, canvas_y)
        )
        if clicked_item_id in overlapping:
            overlapping.remove(clicked_item_id)
        try:
            clicked_item_id = get_highest_in_stacking_order(overlapping, canvas)
        except IndexError:
            clicked_item_id = None

    events.post(
        Event.CANVAS_LEFT_CLICK,
        canvas,
        canvas_x,
        canvas_y,
        clicked_item_id,
        modifier=modifier,
        double=double,
    )


def on_right_click(event: tk.Event, modifier: ModifierEnum, double: bool):
    canvas = event.widget
    canvas_x = canvas.canvasx(event.x)
    canvas_y = canvas.canvasx(event.y)
    clicked_item_id = next(iter(canvas.find_withtag(tk.CURRENT)), None)

    if clicked_item_id and CLICK_THROUGH in canvas.gettags(clicked_item_id):
        overlapping = set(
            canvas.find_overlapping(canvas_x, canvas_y, canvas_x, canvas_y)
        )
        if clicked_item_id in overlapping:
            overlapping.remove(clicked_item_id)
        try:
            clicked_item_id = get_highest_in_stacking_order(overlapping, canvas)
        except IndexError:
            clicked_item_id = None

    events.post(
        Event.CANVAS_RIGHT_CLICK,
        canvas,
        canvas_x,
        canvas_y,
        clicked_item_id,
        modifier=modifier,
        double=double,
    )
