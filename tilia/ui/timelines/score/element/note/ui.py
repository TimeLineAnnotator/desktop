from __future__ import annotations
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QGraphicsScene,
    QGraphicsItem,
)

from tilia.requests import Post, post
from tilia.ui.timelines.score import attrs
from tilia.ui.color import get_tinted_color
from tilia.ui.format import format_media_time
from tilia.ui.consts import TINT_FACTOR_ON_SELECTION
from tilia.ui.coords import get_x_by_time
from tilia.settings import settings
from tilia.ui.timelines.base.element import TimelineUIElement
from tilia.ui.timelines.score.element.note.body import NoteBody
from tilia.ui.timelines.score.element.note.supplementary_line import NoteSupplementaryLine

if TYPE_CHECKING:
    from tilia.ui.timelines.score.timeline import NoteTimelineUI


class NoteUI(TimelineUIElement):
    LABEL_MARGIN = 3

    INSPECTOR_FIELDS = attrs.INSPECTOR_FIELDS

    FIELD_NAMES_TO_ATTRIBUTES = attrs.FIELD_NAMES_TO_ATTRIBUTES

    UPDATE_TRIGGERS = ["color"]

    CONTEXT_MENU_CLASS = None

    def __init__(
        self,
        id: int,
        timeline_ui: NoteTimelineUI,
        scene: QGraphicsScene,
        **_,
    ):
        super().__init__(id=id, timeline_ui=timeline_ui, scene=scene)

        self._setup_body()

    def _setup_body(self):
        self.body = NoteBody(self.start_x, self.end_x, self.top_y, self.note_height(), self.ui_color)
        self.supplementary_line = NoteSupplementaryLine(*self.get_supplementary_line_args())
        self.scene.addItem(self.body)
        self.scene.addItem(self.supplementary_line)
        
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

    def get_supplementary_line_args(self):
        return self.start_x - self.supplementary_line_offset(), self.end_x + self.supplementary_line_offset(), self.top_y + self.note_height() / 2

    def update_color(self):
        self.body.set_fill(self.ui_color)

    def update_position(self):
        self.update_time()

    def update_time(self):
        self.body.set_position(self.start_x, self.end_x, self.top_y, self.note_height())
        self.supplementary_line.set_position(*self.get_supplementary_line_args())

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
            "End": format_media_time(self.get_data('end')),
            "Pitch class": self.get_data('pitch_class'),
            "Comments": self.get_data("comments"),
        }
