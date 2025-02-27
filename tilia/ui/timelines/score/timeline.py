from __future__ import annotations

import math
from typing import Callable, Any, Iterable

from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtWidgets import QGraphicsRectItem

from tilia.dirs import IMG_DIR
from tilia.exceptions import GetComponentDataError, NoReplyToRequest
from tilia.requests import Get, get, listen, Post, post
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.settings import settings
from tilia.ui.color import get_tinted_color
from tilia.ui.consts import TINT_FACTOR_ON_SELECTION
from tilia.ui.coords import time_x_converter
from tilia.ui.smooth_scroll import setup_smooth, smooth
from tilia.ui.timelines.base.timeline import TimelineUI
from tilia.ui.timelines.collection.requests.enums import ElementSelector
from tilia.ui.timelines.cursors import CursorMixIn
from tilia.ui.timelines.drag import DragManager
from tilia.ui.timelines.score.context_menu import ScoreTimelineUIContextMenu
from tilia.ui.timelines.score.element import (
    NoteUI,
    StaffUI,
    ClefUI,
    BarLineUI,
    TimeSignatureUI,
    KeySignatureUI,
)
from tilia.ui.timelines.score.element.with_collision import (
    TimelineUIElementWithCollision,
)
from tilia.ui.timelines.score.request_handlers import (
    ScoreTimelineUIElementRequestHandler,
)
from tilia.ui.timelines.score.toolbar import ScoreTimelineToolbar
from tilia.ui.windows.svg_viewer import SvgViewer


class ScoreTimelineUI(TimelineUI):
    TOOLBAR_CLASS = ScoreTimelineToolbar
    ACCEPTS_HORIZONTAL_ARROWS = True

    TIMELINE_KIND = TimelineKind.SCORE_TIMELINE
    ELEMENT_CLASS = [
        NoteUI,
        StaffUI,
        BarLineUI,
        ClefUI,
        TimeSignatureUI,
        KeySignatureUI,
    ]

    CONTEXT_MENU_CLASS = ScoreTimelineUIContextMenu

    STAFF_MIN_HEIGHT = 150
    SYMBOLS_ABOVE_STAFF_MAX_HEIGHT = 50

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.UPDATE_TRIGGERS = self.UPDATE_TRIGGERS + ["svg_data"]
        listen(
            self,
            Post.SETTINGS_UPDATED,
            self.on_settings_updated,
        )
        listen(self, Post.PLAYER_CURRENT_TIME_CHANGED, self.on_audio_time_change)
        listen(self, Post.TIMELINE_WIDTH_SET_DONE, self.on_timeline_width_set_done)

        self._setup_pixmaps()
        self._reset_caches()
        self.update_height()
        self._setup_svg_view()

        listen(
            self,
            Post.SCORE_TIMELINE_COMPONENTS_DESERIALIZED,
            self.on_score_timeline_components_deserialized,
        )
        listen(
            self,
            Post.SCORE_TIMELINE_CLEAR_DONE,
            self.on_score_timeline_clear_done,
        )

    def _setup_pixmaps(self):
        self.pixmaps = {
            "time signature": {
                n: QPixmap(self.get_time_signature_pixmap_path(n)) for n in range(10)
            },
        }

    @property
    def svg_view(self):
        try:
            return get(Get.SCORE_VIEWER, self.id)
        except NoReplyToRequest:
            viewer = SvgViewer(name=self.get_data("name"), tl_id=self.id)
            if self.timeline.svg_data:
                viewer.load_svg_data(self.timeline.svg_data)
                self.measure_tracker.setVisible(not viewer.is_hidden)
            return viewer

    @staticmethod
    def get_time_signature_pixmap_path(n: int) -> str:
        return str((IMG_DIR / f"time-signature-{n}.svg").resolve())

    def on_settings_updated(self, updated_settings):
        if "score_timeline" in updated_settings:
            self.measure_tracker.update_color()

    def on_timeline_element_request(
        self, request, selector: ElementSelector, *args, **kwargs
    ):
        return ScoreTimelineUIElementRequestHandler(self).on_request(
            request, selector, *args, **kwargs
        )

    def update_name(self):
        name = self.get_data("name")
        self.scene.set_text(name)
        if self.svg_view:
            self.svg_view.update_title(name)

    def get_staff_y_cache(self):
        return {
            index: (staff.top_y(), staff.bottom_y())
            for index, staff in self.staff_cache.items()
        }

    def get_staves_y_coordinates(self):
        if not self.staff_y_cache:
            self.staff_y_cache = self.get_staff_y_cache()
        return [(top, bottom) for top, bottom in self.staff_y_cache.values()]

    def get_staff_top_y(self, index: int) -> float:
        staff = self.staff_cache.get(index)
        return staff.top_y() if staff else 0

    def get_staff_bottom_y(self, index: int) -> float:
        staff = self.staff_cache.get(index)
        return staff.bottom_y() if staff else 0

    def get_staff_middle_y(self, index: int) -> float:
        if not self.staff_heights:
            return index * self.STAFF_MIN_HEIGHT + self.STAFF_MIN_HEIGHT / 2

        cumulative_height = 0
        for j, value in sorted(self.staff_heights.items(), key=lambda x: x[0]):
            if j == index:
                return cumulative_height + value / 2
            else:
                cumulative_height += value

    def get_scale_for_symbols_above_staff(self) -> float:
        visibility_treshold = 10
        max_size_treshold = 280
        min_scale = 0.4
        average_measure_width = self.average_measure_width()
        if not average_measure_width:
            return 1.0
        if average_measure_width < visibility_treshold:
            return 0
        return min(
            1.0, min_scale + (average_measure_width / max_size_treshold * min_scale)
        )

    def get_height_for_symbols_above_staff(self) -> int:
        return int(
            self.SYMBOLS_ABOVE_STAFF_MAX_HEIGHT
            * self.get_scale_for_symbols_above_staff()
        )

    def get_height(self):
        if not self.staff_heights:
            return self.STAFF_MIN_HEIGHT
        return sum(self.staff_heights.values())

    def get_y_for_symbols_above_staff(self, staff_index: int) -> int:
        if not self.staff_heights:
            return self.STAFF_MIN_HEIGHT * staff_index

        cumulative_height = 0
        for j, value in self.staff_heights.items():
            if j == staff_index:
                return cumulative_height
            else:
                cumulative_height += value

    def on_timeline_component_created(
        self,
        kind: ComponentKind,
        id: int,
        get_data: Callable[[str], Any],
        set_data: Callable[[str, Any], None],
    ):
        element = super().on_timeline_component_created(kind, id, get_data, set_data)
        if kind == ComponentKind.STAFF:
            self.update_height()
            self.staff_cache[element.get_data("index")] = element
            return
        elif kind == ComponentKind.BAR_LINE:
            self._measure_count += 1
            if not self.first_bar_line:
                self.first_bar_line = element
                self.last_bar_line = element
            elif get_data("time") > self.last_bar_line.get_data("time"):
                self.last_bar_line = element
            elif get_data("time") == self.last_bar_line.get_data("time"):
                self.last_bar_line = element
        elif kind == ComponentKind.NOTE:
            self._update_staff_extreme_notes(element.get_data("staff_index"), element)

        try:
            time = element.get_data("time")
            staff_index = element.get_data("staff_index")
        except GetComponentDataError:
            return
        if overlapping_components := self._get_overlap(staff_index, time, kind):
            self._add_to_overlapping_elements(overlapping_components)
            self._offset_overlapping_elements(overlapping_components)

        if kind == ComponentKind.CLEF:
            # Clefs need to be frequently found by time,
            # so we cache them here
            self.clef_time_cache = self.get_clef_time_cache()

    def _update_staff_extreme_notes(self, staff_index: int, note: NoteUI) -> None:
        pitch = note.get_data("pitch")
        if staff_index not in self.staff_extreme_notes:
            self.staff_extreme_notes[staff_index] = {"low": note, "high": note}
        elif pitch < self.staff_extreme_notes[staff_index]["low"].get_data("pitch"):
            self.staff_extreme_notes[staff_index]["low"] = note
        elif pitch > self.staff_extreme_notes[staff_index]["high"].get_data("pitch"):
            self.staff_extreme_notes[staff_index]["high"] = note

    def _update_staff_heights(self) -> None:
        min_margin_top = 50
        min_margin_bottom = 30
        staff_heights = {}
        for i, notes in self.staff_extreme_notes.items():
            bottom = (
                max(
                    notes["low"].top_y + notes["low"].note_height(),
                    self.get_staff_bottom_y(i),
                )
                + min_margin_bottom
            )
            top = min(notes["high"].top_y, self.get_staff_top_y(i)) - min_margin_top

            staff_heights[i] = int(bottom - top)

        self.staff_heights = staff_heights

    def get_clef_time_cache(self) -> dict[int, dict[tuple[int, int], ClefUI]]:
        cache = {}
        all_clefs = self.element_manager.get_elements_by_attribute(
            "kind", ComponentKind.CLEF
        )
        for idx in set([clef.get_data("staff_index") for clef in all_clefs]):
            clefs_in_staff = [
                clef for clef in all_clefs if clef.get_data("staff_index") == idx
            ]
            cache[idx] = {}
            prev_clef = clefs_in_staff[0]
            start_time = prev_clef.get_data("time")
            for clef in clefs_in_staff[1:]:
                time = clef.get_data("time")
                cache[idx][(start_time, time)] = prev_clef
                start_time = time
                prev_clef = clef

            cache[idx][(start_time, get(Get.MEDIA_DURATION))] = clefs_in_staff[-1]
        return cache

    def get_clef_by_time(self, time: float, staff_index: int) -> ClefUI | None:
        if staff_index not in self.clef_time_cache:
            return None
        for start, end in self.clef_time_cache[staff_index].keys():
            if start <= time < end:
                return self.clef_time_cache[staff_index][(start, end)]

    def _get_overlap(
        self, staff_index: float, time: float, kind: ComponentKind
    ) -> tuple[TimelineUIElementWithCollision]:
        # Elements will be displayed in the order below
        overlapping_kinds = [
            ComponentKind.CLEF,
            ComponentKind.KEY_SIGNATURE,
            ComponentKind.TIME_SIGNATURE,
        ]

        if kind not in overlapping_kinds:
            return tuple()

        overlapping = [
            c
            for c in self
            if c.kind in overlapping_kinds
            and c.get_data("time") == time
            and c.get_data("staff_index") == staff_index
        ]
        overlapping = tuple(
            sorted(overlapping, key=lambda c: overlapping_kinds.index(c.kind))
        )
        return overlapping if len(overlapping) > 1 else tuple()

    @staticmethod
    def _get_offsets_for_overlapping_elements(
        overlapping_elements: Iterable[TimelineUIElementWithCollision],
    ):
        mid_x = sum([c.width for c in overlapping_elements]) / 2
        element_to_offset = {}
        total_width = 0

        for element in overlapping_elements:
            element_to_offset[element] = total_width - mid_x

            total_width += element.width

        return element_to_offset

    def _offset_overlapping_elements(
        self, elements: tuple[TimelineUIElementWithCollision]
    ):
        component_to_offset = self._get_offsets_for_overlapping_elements(elements)
        for elm in elements:
            elm.x_offset = component_to_offset[elm]

    def _add_to_overlapping_elements(
        self, group: tuple[TimelineUIElementWithCollision]
    ):
        for existing_group in self.overlapping_elements.copy():
            if any(element in existing_group for element in group):
                self.overlapping_elements.remove(existing_group)
                break

        self.overlapping_elements.add(group)

    def update_overlapping_elements_offsets(self):
        for group in self.overlapping_elements:
            self._offset_overlapping_elements(group)

    def get_staff_bounding_steps(
        self, time: float, staff_index: int
    ) -> tuple[tuple[int, int], tuple[int, int]] | None:
        """
        Returns a tuple of the form ((step_lower, octave_lower), (step_upper, octave_upper)) where:
        - step_lower is the step of the lowest staff line
        - octave_lower is the octave of the lowest staff line
        - step_upper is the step of the highest staff line
        - octave_upper is the octave of the highest staff line
        The earliest staff before time + 0.01 will be used. Returns None if there is no such staff.
        """
        staff = self.staff_cache.get(staff_index)
        clef = self.get_clef_by_time(time, staff_index)
        if not staff:
            return None
        line_count = staff.get_data("line_count")
        clef_step = clef.get_data("step")
        clef_octave = clef.get_data("octave")
        clef_line_number = clef.get_data("line_number")

        upper_line_number = math.floor(line_count / 2)
        upper_step_diff = (upper_line_number - clef_line_number) * 2
        upper_step = clef_step + upper_step_diff
        upper_step_octave_diff = upper_step // 7

        lower_line_number = math.floor(line_count / 2) * -1
        lower_step_diff = (lower_line_number - clef_line_number) * 2
        lower_step = clef_step + lower_step_diff
        lower_step_octave_diff = lower_step // 7
        while lower_step < 0:
            lower_step += 7

        return (lower_step, clef_octave + lower_step_octave_diff), (
            upper_step % 7,
            clef_octave + upper_step_octave_diff,
        )

    def update_height(self):
        self.scene.set_height(int(self.get_height()))
        self.view.set_height(int(self.get_height()))

    def set_width(self, width):
        super().set_width(width)
        self.update_overlapping_elements_offsets()
        # self.update_measure_tracker_position()

    def _reset_caches(self):
        self.clef_time_cache: dict[int, dict[tuple[int, int], ClefUI]] = {}
        self.staff_cache: dict[int, StaffUI] = {}
        self.staff_y_cache: dict[int, tuple[int, int]] = {}
        self.first_bar_line: BarLineUI | None = None
        self.last_bar_line: BarLineUI | None = None
        self.staff_extreme_notes: dict[int, dict[str, NoteUI]] = {}
        self.staff_heights: dict[int, float] = {}
        self._measure_count = 0  # assumes measures can't be deleted
        self.overlapping_elements = set()

    def on_score_timeline_clear_done(self, id: int):
        if id != self.id:
            return
        self._reset_caches()
        self.reset_svg()

    def on_score_timeline_components_deserialized(self, id: int):
        if id != self.id:
            return

        self._update_staff_heights()

        for element in self.staff_cache.values():
            element.on_components_deserialized()

        self.staff_y_cache = self.get_staff_y_cache()

        for element in self.elements:
            if element.kind in [
                ComponentKind.STAFF,
                ComponentKind.SCORE_ANNOTATION,
            ]:
                continue
            element.on_components_deserialized()

        self.update_height()
        self.collection.update_timeline_uis_position()

    def average_measure_width(self) -> float:
        if self._measure_count == 0:
            return 0
        x0 = self.first_bar_line.x()
        x1 = self.last_bar_line.x()
        return (x1 - x0) / self._measure_count

    def on_audio_time_change(self, time: float, _) -> None:
        if self.svg_view.is_svg_loaded:
            self.svg_view.scroll_to_time(time, False)

    def _setup_svg_view(self) -> None:
        self.tracker_start = 0
        self.tracker_end = 0
        self.dragged = False
        setup_smooth(self)
        self.measure_tracker = MeasureTracker()
        self.scene.addItem(self.measure_tracker)

        if self.timeline.svg_data:
            viewer = SvgViewer(name=self.get_data("name"), tl_id=self.id)
            viewer.load_svg_data(self.timeline.svg_data)
            self.measure_tracker.show()

    def update_svg_data(self) -> None:
        self.svg_view.load_svg_data(self.timeline.svg_data)

    def reset_svg(self):
        self.svg_view.deleteLater()

    def on_left_click(self, item, modifier, double, x, y):
        if item != self.measure_tracker:
            return super().on_left_click(item, modifier, double, x, y)
        self.setup_drag()

    def setup_drag(self) -> None:
        DragManager(
            get_min_x=lambda: get(Get.LEFT_MARGIN_X),
            get_max_x=lambda: get(Get.RIGHT_MARGIN_X),
            before_each=self.before_each_drag,
            after_each=self.after_each_drag,
            on_release=self.on_drag_end,
        )

    def before_each_drag(self):
        if not self.dragged:
            self.dragged = True
            post(Post.ELEMENT_DRAG_START)

    def after_each_drag(self, drag_x: int):
        self.svg_view.scroll_to_time(time_x_converter.get_time_by_x(drag_x), True)

    def on_drag_end(self):
        if self.dragged:
            post(Post.ELEMENT_DRAG_END)
        self.dragged = False

    def update_measure_tracker_position(
        self, start: float | None = None, end: float | None = None
    ) -> None:
        def __get_tracker_position() -> QPointF:
            return QPointF(self.tracker_start, self.tracker_end)

        @smooth(self, __get_tracker_position)
        def __set_tracker_position(point: QPointF):
            self.tracker_start = point.x()
            self.tracker_end = point.y()
            __update_position()

        def __update_position():
            self.measure_tracker.update_position(
                time_x_converter.get_x_by_time(self.tracker_start),
                time_x_converter.get_x_by_time(self.tracker_end),
                self.view.height(),
            )

        if not (start or end):
            __update_position()
        else:
            __set_tracker_position(QPointF(start, end))

    def on_timeline_width_set_done(self, _: float) -> None:
        if self.svg_view and self.svg_view.is_svg_loaded:
            self.update_measure_tracker_position()


class MeasureTracker(CursorMixIn, QGraphicsRectItem):
    def __init__(self) -> None:
        super().__init__(cursor_shape=Qt.CursorShape.SizeHorCursor)
        self.update_color()

    def update_position(self, start: float, end: float, height: float) -> None:
        self.setRect(QRectF(start, 0, end - start, height))
        self.setZValue(-10)

    def update_color(self) -> None:
        color = settings.get("score_timeline", "measure_tracker_color")
        self.setBrush(QColor(color))
        self.setPen(
            QColor(
                get_tinted_color(
                    color,
                    TINT_FACTOR_ON_SELECTION,
                )
            )
        )
