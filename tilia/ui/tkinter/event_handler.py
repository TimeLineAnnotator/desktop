import tkinter as tk
import tilia.globals_ as globals_
import tilia.events as events

# COMMON FUNCTIONS #
from tilia.events import EventName
from tilia.ui.tkinter.modifier_enum import ModifierEnum


def marker_at_slider(_):
    """Request marker at current slider position"""

    suitable_types = ("FreeMarkerTimeline",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        timeline.marker(globals_.SLIDER_TIMELINE.slider.pos)


def beat_marker_at_slider(_):
    """Request marker at current slider position"""

    suitable_types = ("BeatTimeline",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        timeline.marker(globals_.SLIDER_TIMELINE.slider.pos)


def on_playpause(_=None):
    """Handles pressing of the play\pause button"""
    paused = globals_.PLAYER.play_pause()

    if paused:
        icon = "pause"
    else:
        icon = "play"

    globals_.APP.change_playpause_icon(icon)


def on_stop(_=None):
    """Handles pressing of the stop button"""
    globals_.PLAYER.stop()


# MOUSE AND KEYBOARD EVENTS #


def on_shift_click(_):
    """Handles clicking with shift pressed"""

    suitable_types = (
        "HierarchyTimeline",
        "BeatTimeline",
        "FreeMarkerTimeline",
        "RangeTimeline",
    )
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        clicked_item = timeline.canvas.find_withtag(tk.CURRENT)

        if clicked_item:  # check if something is clicked
            # check if clicked item is selected
            if "selected" not in timeline.canvas.gettags(clicked_item):
                timeline.select_by_id(clicked_item[0])
            else:
                timeline.deselect(clicked_item[0])


def on_click(event, modifier: ModifierEnum):
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


def on_right_click(event):
    """Handles right clicking"""
    events.post(EventName.RIGHT_BUTTON_CLICK, event)


def on_left_arrow(_):
    suitable_types = ("FreeMarkerTimeline", "BeatTimeline", "HierarchyTimeline")
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        timeline.on_arrow_key("left")


def on_right_arrow(_):
    suitable_types = ("FreeMarkerTimeline", "BeatTimeline", "HierarchyTimeline")
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        timeline.on_arrow_key("right")


def on_up_arrow(_):
    suitable_types = ("HierarchyTimeline",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        timeline.on_arrow_key("up")


def on_down_arrow(_):
    suitable_types = ("HierarchyTimeline",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        timeline.on_arrow_key("down")


def on_shift_up_arrow(_):
    suitable_types = ("HierarchyTimeline",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        timeline.on_shift_arrow_key("up")


def on_shift_down_arrow(_):
    suitable_types = ("HierarchyTimeline",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        timeline.on_shift_arrow_key("down")


def on_shift_right_arrow(_):
    suitable_types = ("HierarchyTimeline",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        timeline.on_shift_arrow_key("right")


def on_shift_left_arrow(_):
    suitable_types = ("HierarchyTimeline",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        timeline.on_shift_arrow_key("left")


def on_release(event):
    """Handles release of the mouse button"""
    pass
    #
    # timeline = find_timeline_for_binding(("all",))
    #
    # if timeline:
    #
    #     if globals_.DRAGGING:
    #         timeline.hdrag_stop(event)
    #         globals_.DRAGGING = False
    #
    #     timeline.on_release()
    #
    #     # for refactored timelines
    #     events.post(EventsEnum.TIMELINE_LEFT_RELEASED)


def on_double_click(event):
    """Handles double clicking"""

    suitable_types = (
        "HierarchyTimeline",
        "BeatTimeline",
        "FreeMarkerTimeline",
        "SliderTimeline",
        "RangeTimeline",
    )
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        clicked_item = timeline.canvas.find_withtag(tk.CURRENT)

        if clicked_item != ():
            timeline.on_double_click(clicked_item[0], event.x, event.y)


def on_delete(_):
    events.post(EventName.KEY_PRESS_DELETE)


def delete_units(_=None):
    """Handle pressing of the delete key"""
    suitable_types = (
        "HierarchyTimeline",
        "BeatTimeline",
        "FreeMarkerTimeline",
        "RangeTimeline",
    )

    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        canvas_ids = [obj.canvas_id for obj in timeline.selected_objects]
        timeline.delete_by_id(canvas_ids)


def on_clear_timelines():
    """Clear timeline"""
    globals_.APP.clear()


# BUTTON EVENTS #


def on_split_button():
    """Handle pressing of the Split button"""

    split_at_slider(None)


def on_delete_unit_button():
    timeline = find_timeline_for_binding(("all",))

    from tilia.timelines.hierarchy import components

    # if timeline.selected_class == hierarchies.Hierarchy:
    #     for obj in timeline.selected_objects:
    #         obj.delete()


def on_add_beat_button():
    """Handles pressing of the Add beat button"""

    suitable_types = ("BeatTimeline",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        timeline.marker(globals_.CURRENT_TIME)


def on_paste_unit_button():
    suitable_types = ("HierarchyTimeline",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        timeline.paste()


def on_paste_unit_with_children_button():
    paste_all_attributes()


def on_change_beat_number_button():
    timeline = find_timeline_for_binding(("all",))

    import tilia.markers as markers

    if (
        timeline.selected_class == markers.BeatMarker
        and timeline.selected_cardinality == "single"
    ):
        timeline.selected_object.beat.measure.ask_change_number()


def on_reset_beat_number_button():
    timeline = find_timeline_for_binding(("all",))

    import tilia.markers as markers

    if (
        timeline.selected_class == markers.BeatMarker
        and timeline.selected_cardinality == "single"
    ):
        timeline.selected_object.beat.measure.reset_number()


def on_distribute_beats_button():
    timeline = find_timeline_for_binding(("all",))

    import tilia.markers as markers

    if timeline.selected_class == markers.BeatMarker:
        if timeline.selected_cardinality == "single":
            timeline.distribute_beats_single()
        elif timeline.selected_cardinality == "multiple":
            timeline.distribute_beats_multiple()


def on_add_marker_button():
    suitable_types = ("FreeMarkerTimeline",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        timeline.marker(globals_.SLIDER_TIMELINE.slider.pos)


def on_edit_marker_button():
    timeline = find_timeline_for_binding(("all",))

    import tilia.markers as markers

    if timeline.selected_class == markers.FreeMarker:
        if timeline.selected_cardinality == "single":
            markers.MarkerEditWindow(timeline, timeline.selected_object)


def on_delete_marker_button():
    timeline = find_timeline_for_binding(("all",))

    import tilia.markers as markers

    if timeline.selected_class == markers.FreeMarker:
        for obj in timeline.selected_objects:
            obj.delete()


def on_change_level_button(plus_minus):
    """Handle pressing of the change level buttons"""

    suitable_types = ("HierarchyTimeline",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:

        selected_units = timeline.get_selected_objects("Hierarchy")

        if selected_units:
            if plus_minus == "plus":
                selected_units = reversed(
                    sorted(selected_units, key=lambda x: getattr(x, "level"))
                )
                for unit in selected_units:
                    unit.change_level_by_amount(1)
            elif plus_minus == "minus":
                selected_units = sorted(
                    selected_units, key=lambda x: getattr(x, "level")
                )
                for unit in selected_units:
                    unit.change_level_by_amount(-1)


def on_delete_beat_button():
    timeline = find_timeline_for_binding(("all",))

    import tilia.markers as markers

    if timeline.selected_class == markers.BeatMarker:
        for obj in timeline.selected_objects:
            obj.delete()


def on_find_go_beat_button():
    events.post(EventName.GO_TO_MEASURE_OPEN)


def on_create_child_button():
    """Handle clicking of the Create Child button"""

    suitable_types = ("HierarchyTimeline",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:

        selected_units = timeline.get_selected_objects("Hierarchy")

        if selected_units:
            for unit in selected_units:
                unit.create_unit_below()


def on_group_button(_=None):
    """Handle clicking of the Group button"""

    suitable_types = ("HierarchyTimeline",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:

        selected_units = timeline.get_selected_objects("Hierarchy")

        if selected_units:
            timeline.units.group(selected_units)


def on_shift_m(_):
    on_merge_button()


def on_merge_button():
    """Handle clicking of the Merge button"""

    suitable_types = ("HierarchyTimeline",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:

        selected_units = timeline.get_selected_objects("Hierarchy")

        if selected_units:
            timeline.units.merge(selected_units)


def on_shift_b(_):
    """Creates children below selected hierarchy"""
    on_create_child_button()


def on_toggle_range_creation_button(_=None):
    suitable_types = ("RangeTimeline",)
    timeline = find_timeline_for_binding(suitable_types)
    if timeline:
        timeline.on_range_creation_button()


# MENU HANDLERS #


def on_save(save_as=True):
    """Handle pressing of the save button"""
    events.post(EventName.FILE_SAVE_AS)


def on_new():
    """Handles pressing of the New... button"""
    events.post(EventName.FILE_NEW)


def on_open():
    """Handle pressing of the open button"""
    events.post(EventName.FILE_OPEN)


def on_load_song():
    """Handle pressing of the Load audio button"""
    events.post(EventName.FILE_LOAD_MEDIA)


def on_metadata():
    """Handle pressing of the _media_metadata button"""
    events.post(EventName.METADATA_WINDOW_OPEN)


def on_ctrlc(_):
    """Copies currently selected object"""

    suitable_types = ("all",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        timeline.copy()


def on_ctrl_g(_):
    """Opens Go to measure window"""
    events.post(EventName.GO_TO_MEASURE_OPEN)


def on_ctrlv(_):
    """Pastes clipboard object to currently selected object"""

    suitable_types = ("all",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        timeline.paste()


def paste_all_attributes():
    suitable_types = ("HierarchyTimeline",)
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:

        selected_units = timeline.get_selected_objects("Hierarchy")

        for unit in selected_units:
            unit.special_receive_paste(globals_.clipboard[0])


def on_ctrl_shift_v(_):
    """Pastes clipboard object to currently selected object"""
    paste_all_attributes()


def on_ctrlz(_=None):
    """Handle pressing of Ctrl + Z"""

    suitable_types = (
        "HierarchyTimeline",
        "BeatTimeline",
        "FreeMarkerTimeline",
        "RangeTimeline",
    )
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        timeline.undo()

        # for future implementation
        # globals_.TIMELINE_STATE_STACK_MANAGER.undo()


def on_ctrly(_=None):
    """Handle pressing of Ctrl + Y"""

    suitable_types = (
        "HierarchyTimeline",
        "BeatTimeline",
        "FreeMarkerTimeline",
        "RangeTimeline",
    )
    timeline = find_timeline_for_binding(suitable_types)

    if timeline:
        timeline.redo()

        # for future implementation
        # globals_.TIMELINE_STATE_STACK_MANAGER.redo()


def find_timeline_for_binding(suitable_types: tuple[str, ...]):
    """Returns last selected timeline of type suitable for binding"""

    if "all" in suitable_types:
        return globals_.TIMELINE_COLLECTION.select_order[0]

    for timeline in globals_.TIMELINE_COLLECTION.select_order:
        if timeline.__class__.__name__ in suitable_types:
            return timeline


class TkEventHandler:
    DEFAULT_CANVAS_BINDINGS = [
        # NEW BINDINGS
        ("<ButtonPress-1>", lambda event: on_click(event, modifier=ModifierEnum.NONE)),
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
        (
            "<Control-D>",
            lambda _: events.post(EventName.DEBUG_SELECTED_ELEMENTS),
        ),
        ("<Delete>", on_delete),
        (
            "<Control-i>",
            lambda _: events.post(EventName.UI_REQUEST_WINDOW_INSPECTOR),
        ),
    ]

    DEFAULT_TOP_LEVEL_BINDINGS = [("<F2>", beat_marker_at_slider)]

    def __init__(self, root: tk.Tk):
        self.root = root
        self._make_default_canvas_bindings()

    def _make_default_canvas_bindings(self) -> None:
        for sequence, callback in self.DEFAULT_CANVAS_BINDINGS:
            self.root.bind_class("Canvas", sequence, callback)

    def on_click(self, event: tk.Event) -> None:
        events.post("")
