from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QGraphicsScene,
    QGraphicsItem,
)

from tilia.requests import Post, post
from tilia.timelines.score.components.note import pitch
from tilia.ui.timelines.score import attrs
from tilia.ui.color import get_tinted_color
from tilia.ui.format import format_media_time
from tilia.ui.consts import TINT_FACTOR_ON_SELECTION
from tilia.ui.coords import get_x_by_time
from tilia.settings import settings
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.timelines.score.element.note.accidental import NoteAccidental
from tilia.ui.timelines.score.element.note.body import NoteBody
from tilia.ui.timelines.score.element.note.supplementary_line import (
    NoteSupplementaryLines,
)

if TYPE_CHECKING:
    from tilia.ui.timelines.score.timeline import ScoreTimelineUI


class NoteUI(TimelineUIElement):
    LABEL_MARGIN = 3

    INSPECTOR_FIELDS = attrs.INSPECTOR_FIELDS

    FIELD_NAMES_TO_ATTRIBUTES = attrs.FIELD_NAMES_TO_ATTRIBUTES

    UPDATE_TRIGGERS = ["color"]

    CONTEXT_MENU_CLASS = None

    def __init__(
        self,
        id: int,
        timeline_ui: ScoreTimelineUI,
        scene: QGraphicsScene,
        **_,
    ):
        super().__init__(id=id, timeline_ui=timeline_ui, scene=scene)

        self._setup_body()
        self._setup_supplementary_line()
        self._setup_accidental()

    def _setup_body(self):
        self.body = NoteBody(
            self.start_x, self.end_x, self.top_y, self.note_height(), self.ui_color
        )
        self.scene.addItem(self.body)

    def _setup_supplementary_line(self):
        bounding_steps = self.timeline_ui.get_staff_bounding_steps(self.get_data('start'))
        if not bounding_steps:
            # No staff has been created
            self.supplementary_line = None
            return
        (lower_step, upper_step), (lower_octave, upper_octave) = bounding_steps

        my_step = self.get_data('step')
        my_octave = self.get_data('octave')
        my_step_pitch = pitch(my_step, 0, my_octave)

        interval_step = 0
        interval_octave = 0
        if my_step_pitch < pitch(lower_step, 0, lower_octave):
            direction = NoteSupplementaryLines.Direction.DOWN
            interval_step = lower_step - my_step
            interval_octave = my_octave - lower_octave
        elif my_step_pitch > pitch(upper_step, 0, upper_octave):
            direction = NoteSupplementaryLines.Direction.UP
            interval_step = my_step - upper_step
            interval_octave = my_octave - upper_octave

        while interval_octave < 0:
            interval_step = (interval_step - 7) % 7
            interval_octave += 1
        while interval_step < 0:
            interval_step += 7
            interval_octave -= 1

        # Is the case where interval_step, interval_octave == 0, 0 handled correctly?

        supplementary_line_count = math.floor(interval_step / 2)

        if supplementary_line_count:
            self.supplementary_line = NoteSupplementaryLines(
                *self.get_supplementary_line_args(direction, supplementary_line_count),
            )
            for line in self.supplementary_line.lines:
                self.scene.addItem(line)
        else:
            self.supplementary_line = None

    def _setup_accidental(self):
        if self.get_data("display_accidental"):
            accidental_number = self.get_data("accidental")
            self.accidental = NoteAccidental(
                *self.get_accidental_position(accidental_number),
                self.get_accidental_height(accidental_number),
                self.get_accidental_icon_path(accidental_number),
            )
            self.scene.addItem(self.accidental)
        else:
            self.accidental = None

    @property
    def start_x(self):
        return get_x_by_time(self.get_data("start"))
    
    @property
    def end_x(self):
        return get_x_by_time(self.get_data("end"))
    
    @property
    def top_y(self):
        note_height = self.note_height()
        middle_y = self.timeline_ui.get_data('height') / 2
        note_offset = (self.get_data('step') - 6) * note_height / 2
        octave_offset = (self.get_data('octave') - 3) * note_height / 2 * 7
        return middle_y - note_offset - octave_offset - note_height / 2
    
    @property
    def seek_time(self):
        return self.get_data("start")

    @classmethod
    def note_height(cls):
        return settings.get("score_timeline", "note_height")

    @classmethod
    def supplementary_line_offset(cls):
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

    def get_supplementary_line_args(self, direction: NoteSupplementaryLines.Direction, line_count: int):
        return (
            direction,
            line_count,
            *self.get_supplementary_line_position_args(direction),
        )

    def get_supplementary_line_position_args(self, direction: NoteSupplementaryLines.Direction):
        if direction == NoteSupplementaryLines.Direction.UP:
            y1 = self.timeline_ui.get_staff_top_y()
        else:
            y1 = self.timeline_ui.get_staff_bottom_y()
        return self.start_x - self.supplementary_line_offset(), self.end_x + self.supplementary_line_offset(), y1, self.note_height()

    @staticmethod
    def get_accidental_icon_path(accidental: int) -> Path:
        file_name = {
            -2: "double-flat",
            -1: "flat",
            0: "natural",
            1: "sharp",
            2: "double-sharp",
        }[accidental]
        return Path("ui", "img", f"accidental-{file_name}.svg")

    def get_accidental_position(self, accidental: int) -> tuple[float, float]:
        x = self.start_x - 3
        y = self.top_y - self.note_height() / 2
        y_offset = {
            -2: -1,
            -1: -1,
            0: 3,
            1: 3,
            2: 7,
        }[accidental]
        return x, y + y_offset

    @staticmethod
    def get_accidental_height(accidental: int) -> float:
        return {
           -2: 18,
           -1: 18,
            0: 20,
            1: 20,
            2: 12,
        }[accidental]

    def update_color(self):
        self.body.set_fill(self.ui_color)

    def update_position(self):
        self.update_time()

    def update_time(self):
        self.body.set_position(self.start_x, self.end_x, self.top_y, self.note_height())
        if self.supplementary_line:
            self.supplementary_line.set_position(*self.get_supplementary_line_position_args(self.supplementary_line.direction))
        if self.accidental:
            self.accidental.set_position(*self.get_accidental_position(self.get_data('accidental')))

    def child_items(self):
        return [self.body]

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

    def get_inspector_dict(self) -> dict:
        return {
            "Start": format_media_time(self.get_data("start")),
            "End": format_media_time(self.get_data("end")),
            "Pitch class": self.get_data("pitch_class"),
            "Comments": self.get_data("comments"),
        }
