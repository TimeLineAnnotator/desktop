import math
from pathlib import Path

from PySide6.QtWidgets import (
    QGraphicsItem,
)

from tilia.dirs import IMG_DIR
from tilia.requests import Post, post
from tilia.timelines.score.components.note import pitch
from tilia.ui.timelines.score import attrs
from tilia.ui.color import get_tinted_color
from tilia.ui.format import format_media_time
from tilia.ui.consts import TINT_FACTOR_ON_SELECTION
from tilia.ui.coords import time_x_converter
from tilia.settings import settings
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.timelines.harmony.constants import Accidental
from tilia.ui.timelines.score.context_menu import NoteContextMenu
from tilia.ui.timelines.score.element.note.accidental import NoteAccidental
from tilia.ui.timelines.score.element.note.body import NoteBody
from tilia.ui.timelines.score.element.note.ledger_line import (
    NoteLedgerLines,
)


class NoteUI(TimelineUIElement):
    LABEL_MARGIN = 3

    INSPECTOR_FIELDS = attrs.INSPECTOR_FIELDS

    FIELD_NAMES_TO_ATTRIBUTES = attrs.FIELD_NAMES_TO_ATTRIBUTES

    UPDATE_TRIGGERS = ["color"]

    CONTEXT_MENU_CLASS = NoteContextMenu

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.body = None
        self.accidental = None
        self.ledger_line = None

        self._top_y = None

    def _setup_items(self):
        self._setup_body()
        self._setup_ledger_line()
        self._setup_accidental()

    def _setup_body(self):
        self.body = NoteBody(
            self.start_x,
            self.end_x,
            self.top_y,
            self.note_height(),
            self.ui_color,
            self.get_data("tie_type"),
        )
        self.scene.addItem(self.body)

    def _setup_ledger_line(self):
        staff_index = self.get_data("staff_index")
        bounding_steps = self.timeline_ui.get_staff_bounding_steps(
            self.get_data("start"), staff_index
        )
        if not bounding_steps:
            # No staff has been created
            self.ledger_line = None
            return
        (lower_step, lower_octave), (upper_step, upper_octave) = bounding_steps

        my_step = self.get_data("step")
        my_octave = self.get_data("octave")
        my_step_pitch = pitch(my_step, 0, my_octave)

        interval_step = 0
        interval_octave = 0
        if my_step_pitch < pitch(lower_step, 0, lower_octave):
            direction = NoteLedgerLines.Direction.DOWN
            interval_step = lower_step - my_step
            interval_octave = my_octave - lower_octave
            while interval_octave < 0:
                interval_step += 7
                interval_octave += 1

        elif my_step_pitch > pitch(upper_step, 0, upper_octave):
            direction = NoteLedgerLines.Direction.UP
            interval_step = my_step - upper_step
            interval_octave = my_octave - upper_octave
            while interval_octave > 0:
                interval_step += 7
                interval_octave -= 1

        while interval_step < 0:
            interval_step += 7
            interval_octave -= 1

        # Is the case where interval_step, interval_octave == 0, 0 handled correctly?

        ledger_line_count = math.floor(interval_step / 2)

        if ledger_line_count:
            self.ledger_line = NoteLedgerLines(
                *self.get_ledger_line_args(direction, ledger_line_count, staff_index),
            )
            for line in self.ledger_line.lines:
                self.scene.addItem(line)
        else:
            self.ledger_line = None

    def _setup_accidental(self):
        if self.get_data("display_accidental"):
            accidental_number = self.get_data("accidental")
            scale_factor = self.get_accidental_scale_factor()
            self.accidental = NoteAccidental(
                *self.get_accidental_position(accidental_number, scale_factor),
                self.get_accidental_height(accidental_number, scale_factor),
                self.get_accidental_icon_path(accidental_number),
            )
            self.scene.addItem(self.accidental)
        else:
            self.accidental = None

    @property
    def start_x(self):
        return time_x_converter.get_x_by_time(self.get_data("start"))

    @property
    def end_x(self):
        return time_x_converter.get_x_by_time(self.get_data("end"))

    @property
    def clef(self):
        return self.timeline_ui.get_clef_by_time(
            self.get_data("start"), self.get_data("staff_index")
        )

    @property
    def top_y(self):
        if self._top_y is None:
            central_step, central_octave = self.clef.central_step()

            note_height = self.note_height()
            middle_y = self.timeline_ui.get_staff_middle_y(self.get_data("staff_index"))
            note_offset = (self.get_data("step") - central_step) * note_height / 2
            octave_offset = (
                (self.get_data("octave") - central_octave) * note_height / 2 * 7
            )
            self._top_y = middle_y - note_offset - octave_offset - note_height / 2
        return self._top_y

    @property
    def seek_time(self):
        return self.get_data("start")

    @classmethod
    def note_height(cls):
        return settings.get("score_timeline", "note_height")

    @classmethod
    def ledger_line_offset(cls):
        return 5

    @property
    def default_color(self):
        return settings.get("score_timeline", "default_note_color")

    @property
    def ui_color(self):
        base_color = self.get_data("color") or self.default_color
        return (
            base_color
            if not self.is_selected()
            else get_tinted_color(base_color, TINT_FACTOR_ON_SELECTION)
        )

    def clear_cached_top_y(self):
        self._top_y = None

    def get_ledger_line_args(
        self, direction: NoteLedgerLines.Direction, line_count: int, staff_index: int
    ):
        return (
            direction,
            line_count,
            *self.get_ledger_line_position_args(direction, staff_index),
        )

    def get_ledger_line_position_args(
        self, direction: NoteLedgerLines.Direction, staff_index: int
    ):
        if direction == NoteLedgerLines.Direction.UP:
            y1 = self.timeline_ui.get_staff_top_y(staff_index)
        else:
            y1 = self.timeline_ui.get_staff_bottom_y(staff_index)
        return (
            self.start_x - self.ledger_line_offset(),
            self.end_x + self.ledger_line_offset(),
            y1,
            self.note_height(),
        )

    @staticmethod
    def get_accidental_icon_path(accidental: int) -> Path:
        file_name = {
            -2: "double-flat",
            -1: "flat",
            0: "natural",
            1: "sharp",
            2: "double-sharp",
        }[accidental]
        return IMG_DIR / f"accidental-{file_name}.svg"

    def get_accidental_position(
        self, accidental: int, scale_factor: float
    ) -> tuple[float, float]:
        x = self.start_x - 3
        y = self.top_y + self.note_height() / 2
        y_offset = {
            -2: -2,
            -1: -2,
            0: 0,
            1: 0,
            2: 1,
        }[accidental] * scale_factor
        return x, y + y_offset

    @staticmethod
    def get_accidental_height(accidental: int, scale_factor: float) -> int:
        return int(
            {
                -2: 18,
                -1: 18,
                0: 20,
                1: 20,
                2: 12,
            }[accidental]
            * scale_factor
        )

    def get_accidental_scale_factor(self):
        """
        Scales accidental according to amw = average measure width.
        If amw < visibility_treshold, returns 0, indicating accidentals should be hidden.
        If visibility_treshold < amw < max_size_treshold, scales proportionally with min_scale as a minimum.
        If amw > max_size_treshold, returns 1, indicating accidentals should be fully visible.
        """
        visibility_treshold = 30
        max_size_treshold = 180
        min_scale = 0.5
        average_measure_width = self.timeline_ui.average_measure_width()
        if not average_measure_width:
            return 1
        if average_measure_width < visibility_treshold:
            return 0
        return min(
            1, min_scale + (average_measure_width / max_size_treshold * min_scale)
        )

    def update_color(self):
        self.body.set_fill(self.ui_color)

    def update_position(self):
        self.update_time()

    def update_time(self):
        self.body.set_position(self.start_x, self.end_x, self.top_y, self.note_height())
        if self.ledger_line:
            self.ledger_line.set_position(
                *self.get_ledger_line_position_args(
                    self.ledger_line.direction, self.get_data("staff_index")
                )
            )
        if self.accidental:
            accidental = self.get_data("accidental")
            scale_factor = self.get_accidental_scale_factor()
            self.accidental.set_height(
                self.get_accidental_height(accidental, scale_factor)
            )
            self.accidental.set_position(
                *self.get_accidental_position(accidental, scale_factor)
            )

    def child_items(self):
        children = []
        if self.body:
            children.append(self.body)
        if self.ledger_line:
            children += self.ledger_line.lines
        if self.accidental:
            children.append(self.accidental)
        return children

    def left_click_triggers(self) -> list[QGraphicsItem]:
        return [self.body]

    def on_left_click(self, _) -> None:
        pass

    def double_left_click_triggers(self):
        return [self.body]

    def on_double_left_click(self, _):
        post(Post.PLAYER_SEEK, self.seek_time)

    def on_select(self) -> None:
        self.body.on_select()

    def on_deselect(self) -> None:
        self.body.on_deselect()

    def on_components_deserialized(self):
        self._top_y = None  # recalculate since staff position might have changed
        if not self.body:
            self._setup_items()
        else:
            self.update_position()

    def get_inspector_dict(self) -> dict:
        inspector = {
            "Start": format_media_time(self.get_data("start")),
            "End": format_media_time(self.get_data("end")),
            "Comments": self.get_data("comments"),
        }
        inspector["Note"] = "".join(
            [
                chr(65 + (self.get_data("step") - 5) % 7),
                Accidental.get_from_int("frontend", self.get_data("accidental")),
                str(self.get_data("octave")),
            ]
        )
        if start := self.get_data("start_metric_position"):
            end = self.get_data("end_metric_position")
            inspector[
                "Start / end (metric)"
            ] = f"{start.measure}.{start.beat} / {end.measure}.{end.beat}"

        return inspector
