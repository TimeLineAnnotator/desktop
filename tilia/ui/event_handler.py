import sys
import tkinter as tk
import tilia.events as events

from tilia.events import Event
from tilia.ui.canvas_tags import TRANSPARENT, TAG_TO_CURSOR, CURSOR_TAGS
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

current_indicator = 0


def get_highest_in_stacking_order(ids: set, canvas: tk.Canvas) -> int:
    ids_in_order = [id_ for id_ in canvas.find_all() if id_ in ids]
    return ids_in_order[-1]


def get_click_event_params(event: tk.Event) -> tuple[tk.Canvas, int, int, int | None]:
    canvas = event.widget
    canvas_x = canvas.canvasx(event.x)
    canvas_y = canvas.canvasy(event.y)
    id = next(iter(canvas.find_withtag(tk.CURRENT)), None)

    if id and TRANSPARENT in canvas.gettags(id):
        overlapping = set(
            canvas.find_overlapping(canvas_x, canvas_y, canvas_x, canvas_y)
        )
        if id in overlapping:
            overlapping.remove(id)
        try:
            id = get_highest_in_stacking_order(overlapping, canvas)
        except IndexError:
            id = None

    return canvas, canvas_x, canvas_y, id


def on_motion(event: tk.Event) -> None:
    """Sets cursor based on hovered canvas item tags.
    Ignores items tagged with TRANSPARENT"""
    item_id = get_click_event_params(event)[3]

    if not item_id:
        event.widget.config(cursor="")
        return

    for tag in event.widget.gettags(item_id):
        if tag in CURSOR_TAGS:
            event.widget.config(cursor=TAG_TO_CURSOR[tag])
            break
    else:
        event.widget.config(cursor="")


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
    ("<Motion>", on_motion),
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
    ("<Button-4>", lambda _: events.post(Event.REQUEST_ZOOM_IN)),
    ("<Button-5>", lambda _: events.post(Event.REQUEST_ZOOM_OUT)),
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


def on_left_click(event: tk.Event, modifier: ModifierEnum, double: bool):
    """Handles mouse click"""

    events.post(
        Event.CANVAS_LEFT_CLICK,
        *get_click_event_params(event),
        modifier=modifier,
        double=double
    )


def on_right_click(event: tk.Event, modifier: ModifierEnum, double: bool):
    events.post(
        Event.CANVAS_RIGHT_CLICK,
        *get_click_event_params(event),
        modifier=modifier,
        double=double,
        root_x=event.x_root,
        root_y=event.y_root
    )
