from tilia import events
from tilia.events import Event, unsubscribe_from_all


class SelectionBox:
    """Box that indicates objects to be selected when clicking and dragging"""

    def __init__(self, canvas, initial_coord: list[float, float], y_offset: int):
        """
        :param initial_coord: x and y for starting top left corner
        :param y_offset:
        """
        self.upper_left = initial_coord
        self.bottom_right = initial_coord

        self.canvas_id = 0
        self.canvas = canvas
        self._x = self.upper_left[0]
        self.y_offset = y_offset
        self.draw()

        self.setup_overlap()

        # observe mouse movement and release
        events.subscribe(self, Event.TIMELINE_LEFT_BUTTON_DRAG, self.on_motion)
        events.subscribe(
            self, Event.TIMELINE_LEFT_BUTTON_RELEASE, self.on_left_released
        )
        events.subscribe(self, Event.SLIDER_DRAG_START, self.on_preparing_to_drag)
        events.subscribe(self, Event.ELEMENT_DRAG_START, self.on_preparing_to_drag)

    def draw(self):
        self.canvas_id = self.canvas.create_rectangle(*self.get_coords(), fill="")

    def get_coords(self):
        return (
            *self.upper_left,
            self.bottom_right[0],
            self.bottom_right[1] + self.y_offset,
        )

    def setup_overlap(self):
        self.overlap = self.get_canvas_overlap()

        import tkinter as tk

        clicked_item = next(iter(self.canvas.find_withtag(tk.CURRENT)), None)
        if clicked_item:
            events.post(
                Event.SELECTION_BOX_REQUEST_SELECT,
                canvas=self.canvas,
                canvas_item_id=clicked_item,
            )

    def get_canvas_overlap(self):
        overlap = set(self.canvas.find_overlapping(*self.get_coords()))

        try:
            overlap.remove(self.canvas_id)
        except KeyError:
            pass  # happens when SelectionBox is about to be deleted

        return overlap

    def update_position(self):
        self.canvas.coords(self.canvas_id, *self.get_coords())

    def on_motion(self, x1: float, y1: float):
        """Updates selection box size. Returns canvas items that overlap with self."""

        self.bottom_right = [x1, y1]
        self.update_position()

        current_overlap = self.get_canvas_overlap()

        # handle overlap change
        if current_overlap != self.overlap:
            if current_overlap - self.overlap:  # if an object was added
                for canvas_id in (current_overlap - self.overlap).copy():
                    events.post(
                        Event.SELECTION_BOX_REQUEST_SELECT,
                        canvas=self.canvas,
                        canvas_item_id=canvas_id,
                    )
                    self.overlap.add(canvas_id)
            else:  # if an object was removed
                for canvas_id in (self.overlap - current_overlap).copy():
                    events.post(
                        Event.SELECTION_BOX_REQUEST_DESELECT,
                        canvas=self.canvas,
                        canvas_item_id=canvas_id,
                    )
                    self.overlap.remove(canvas_id)

    def on_left_released(self):
        unsubscribe_from_all(self)
        self.canvas.delete(self.canvas_id)

    def on_preparing_to_drag(self):
        unsubscribe_from_all(self)
        self.canvas.delete(self.canvas_id)
