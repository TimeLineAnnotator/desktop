import sys
import tkinter as tk

from tilia.requests import Post, post
from tilia.ui.canvas_tags import TRANSPARENT, TAG_TO_CURSOR, CURSOR_TAGS
from tilia.ui.modifier_enum import ModifierEnum


def on_mouse_wheel(event: tk.Event):
    if sys.platform == "darwin":
        event.delta *= -1

    if event.delta > 0:
        post(Post.REQUEST_ZOOM_IN)
    elif event.delta < 0:
        post(Post.REQUEST_ZOOM_OUT)


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


def on_b1_motion(event: tk.Event) -> None:
    """
    Triggered when dragging with left click
    """
    if not isinstance(event.widget, tk.Canvas):
        return

    post(
        Post.TIMELINE_LEFT_BUTTON_DRAG,
        event.widget.canvasx(event.x),
        event.widget.canvasy(event.y),
        logging_level=5,
    )


def on_motion(event: tk.Event) -> None:
    """Sets cursor based on hovered canvas item tags.
    Ignores items tagged with TRANSPARENT"""
    if not isinstance(event.widget, tk.Canvas):
        return

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
    # -- MOUSE BINDINGS -- #
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
        on_b1_motion
    ),
    ("<Motion>", on_motion),
    (
        "<ButtonRelease-1>",
        lambda _: post(Post.TIMELINE_LEFT_BUTTON_RELEASE),
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
    ("<Button-4>", lambda _: post(Post.REQUEST_ZOOM_IN)),
    ("<Button-5>", lambda _: post(Post.REQUEST_ZOOM_OUT)),
    # -- KEYBOARD BINDINGS -- #
    ("<Delete>", lambda _: post(Post.KEY_PRESS_DELETE)),
    ("<Return>", lambda _: post(Post.KEY_PRESS_ENTER)),
    ("<Left>", lambda _: post(Post.KEY_PRESS_LEFT)),
    ("<Right>", lambda _: post(Post.KEY_PRESS_RIGHT)),
    ("<Up>", lambda _: post(Post.KEY_PRESS_UP)),
    ("<Down>", lambda _: post(Post.KEY_PRESS_DOWN)),
    (
        "<Control-i>",
        lambda _: post(Post.UI_REQUEST_WINDOW_INSPECTOR),
    ),
    ("<Control-c>", lambda _: post(Post.KEY_PRESS_CONTROL_C)),
    ("<Control-v>", lambda _: post(Post.KEY_PRESS_CONTROL_V)),
    ("<Control-V>", lambda _: post(Post.KEY_PRESS_CONTROL_SHIFT_V)),
    ("<Control-z>", lambda _: post(Post.REQUEST_TO_UNDO)),
    ("<Control-y>", lambda _: post(Post.REQUEST_TO_REDO)),
    ("<Control-s>", lambda _: post(Post.REQUEST_SAVE)),
    ("<Control-S>", lambda _: post(Post.REQUEST_SAVE_AS)),
    ("<Control-plus>", lambda _: post(Post.REQUEST_ZOOM_IN)),
    ("<Control-minus>", lambda _: post(Post.REQUEST_ZOOM_OUT)),
    ("<g>", lambda _: post(Post.HIERARCHY_TOOLBAR_GROUP)),
    ("<s>", lambda _: post(Post.HIERARCHY_TOOLBAR_SPLIT)),
    ("<M>", lambda _: post(Post.HIERARCHY_TOOLBAR_MERGE)),
    (
        "<Control-Up>",
        lambda _: post(Post.HIERARCHY_TOOLBAR_LEVEL_INCREASE),
    ),
    (
        "<Control-Down>",
        lambda _: post(Post.HIERARCHY_TOOLBAR_LEVEL_DECREASE),
    ),
    ("<m>", lambda _: post(Post.MARKER_TOOLBAR_BUTTON_ADD)),
    ("<b>", lambda _: post(Post.BEAT_TOOLBAR_BUTTON_ADD)),
    ("<space>", lambda _: post(Post.PLAYER_REQUEST_TO_PLAYPAUSE)),
]


def on_left_click(event: tk.Event, modifier: ModifierEnum, double: bool):
    """Handles mouse click"""
    if not isinstance(event.widget, tk.Canvas):
        return

    post(
        Post.CANVAS_LEFT_CLICK,
        *get_click_event_params(event),
        modifier=modifier,
        double=double
    )


def on_right_click(event: tk.Event, modifier: ModifierEnum, double: bool):
    if not isinstance(event.widget, tk.Canvas):
        return

    post(
        Post.CANVAS_RIGHT_CLICK,
        *get_click_event_params(event),
        modifier=modifier,
        double=double,
        root_x=event.x_root,
        root_y=event.y_root
    )
