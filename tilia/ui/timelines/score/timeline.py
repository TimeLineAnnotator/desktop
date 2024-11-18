from __future__ import annotations

import math

from tilia.exceptions import GetComponentDataError
from tilia.requests import Get, get, listen, Post
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.coords import get_x_by_time
from tilia.ui.timelines.base.timeline import (
    TimelineUI,
)
from tilia.ui.timelines.collection.requests.enums import ElementSelector
from tilia.ui.timelines.score.context_menu import ScoreTimelineUIContextMenu
from tilia.ui.timelines.score.element import NoteUI, StaffUI, ClefUI
from tilia.ui.timelines.score.element.with_collision import TimelineUIElementWithCollision
from tilia.ui.timelines.score.request_handlers import ScoreTimelineUIElementRequestHandler
from tilia.ui.timelines.score.toolbar import ScoreTimelineToolbar


class ScoreTimelineUI(TimelineUI):
    TOOLBAR_CLASS = ScoreTimelineToolbar
    ACCEPTS_HORIZONTAL_ARROWS = True

    TIMELINE_KIND = TimelineKind.SCORE_TIMELINE
    ELEMENT_CLASS = [NoteUI, StaffUI]

    CONTEXT_MENU_CLASS = ScoreTimelineUIContextMenu

    STAFF_VERTICAL_AREA = 150

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        listen(self, Post.SETTINGS_UPDATED, lambda updated_settings: self.on_settings_updated(updated_settings))
        listen(self, Post.SCORE_TIMELINE_COMPONENTS_DESERIALIZED, self.on_score_timeline_components_deserialized)
        self.clef_time_cache: dict[int, dict[tuple[int, int], ClefUI]] = {}
        self.staff_cache: dict[int, StaffUI] = {}
        self._measure_count = self._get_measure_count()

    def _get_measure_count(self):
        return len(self.element_manager.get_elements_by_attribute('kind', ComponentKind.BAR_LINE)) / max(1, len(self.element_manager.get_elements_by_attribute('kind', ComponentKind.STAFF)))

    def on_settings_updated(self, updated_settings):
        if "score_timeline" in updated_settings:
            pass

    def on_timeline_element_request(
        self, request, selector: ElementSelector, *args, **kwargs
    ):
        return ScoreTimelineUIElementRequestHandler(self).on_request(
            request, selector, *args, **kwargs
        )

    def get_staves_y_coordinates(self):
        return [(s.top_y(), s.bottom_y()) for s in self.staff_cache.values()]

    def get_staff_top_y(self, index: int) -> float:
        staff = self.staff_cache.get(index)
        return staff.top_y() if staff else 0

    def get_staff_bottom_y(self, index: int) -> float:
        staff = self.staff_cache.get(index)
        return staff.bottom_y() if staff else 0

    def get_staff_middle_y(self, index: int) -> float:
        return index * self.STAFF_VERTICAL_AREA + self.STAFF_VERTICAL_AREA / 2

    def get_height_for_symbols_above_staff(self) -> int:
        return 50

    def get_y_for_symbols_above_staff(self, staff_index: int) -> int:
        return self.STAFF_VERTICAL_AREA * staff_index

    def on_timeline_component_created(self, kind: ComponentKind, id: int):
        element = super().on_timeline_component_created(kind, id)
        if kind == ComponentKind.STAFF:
            self.update_height()
            self.staff_cache[element.get_data('index')] = element
            return
        elif kind == ComponentKind.BAR_LINE:
            self._measure_count = self._get_measure_count()

        try:
            time = element.get_data('time')
            staff_index = element.get_data('staff_index')
        except GetComponentDataError:
            return
        if overlapping_components := self._get_overlap(staff_index, time, kind):
            component_to_offset = self._get_offsets_for_overlapping_elements(overlapping_components)
            for component in overlapping_components:
                component.x_offset = component_to_offset[component]

        if kind == ComponentKind.CLEF:
            # Clefs need to be frequently found by time,
            # so we cache them here
            self.clef_time_cache = self.get_clef_time_cache()

    def get_clef_time_cache(self) -> dict[int, dict[tuple[int, int], ClefUI]]:
        cache = {}
        start_time = 0
        all_clefs = self.element_manager.get_elements_by_attribute('kind', ComponentKind.CLEF)
        for idx in set([clef.get_data('staff_index') for clef in all_clefs]):
            clefs_in_staff = [clef for clef in all_clefs if clef.get_data('staff_index') == idx]
            cache[idx] = {}
            prev_clef = clefs_in_staff[0]
            for clef in clefs_in_staff[1:]:
                time = clef.get_data('time')
                cache[idx][(start_time, time)] = prev_clef
                start_time = time
                prev_clef = clef

            cache[idx][(start_time, get(Get.MEDIA_DURATION))] = clefs_in_staff[-1]
        return cache

    def get_clef_by_time(self, time: float, staff_index: int) -> ClefUI | None:
        if staff_index not in self.clef_time_cache:
            return None
        for (start, end) in self.clef_time_cache[staff_index].keys():
            if start <= time < end:
                return self.clef_time_cache[staff_index][(start, end)]

    def _get_overlap(self, staff_index: float, time: float, kind: ComponentKind) -> list[TimelineUIElementWithCollision]:
        # Elements will be displayed in the order below
        overlapping_kinds = [ComponentKind.CLEF, ComponentKind.KEY_SIGNATURE, ComponentKind.TIME_SIGNATURE]

        if kind not in overlapping_kinds:
            return []

        overlapping = [c for c in self if c.kind in overlapping_kinds and c.get_data('time') == time and c.get_data('staff_index') == staff_index]
        overlapping = sorted(overlapping, key=lambda c: overlapping_kinds.index(c.kind))
        return overlapping if len(overlapping) > 1 else []

    def _get_offsets_for_overlapping_elements(self, overlapping_elements: list[TimelineUIElementWithCollision]):
        mid_x = sum([c.width for c in overlapping_elements]) / 2
        element_to_offset = {}
        total_width = 0

        for element in overlapping_elements:
            element_to_offset[element] = total_width - mid_x

            total_width += element.width

        return element_to_offset

    def get_staff_bounding_steps(self, time: float, staff_index: int) -> tuple[tuple[int, int], tuple[int, int]] | None:
        """
        Returns a tuple of the form ((step_lower, octave_lower), (step_upper, octave_upper)) where:
        - step_lower is the step of the lowest staff line
        - octave_lower is the octave of the lowest staff line
        - step_upper is the step of the highest staff line
        - octave_upper is the octave of the highest staff line
        The earliest staff before time + 0.01 will be used. Returns None if there is no such staff.
        """
        staff = self.element_manager.get_element_by_attribute('kind', ComponentKind.STAFF)
        clefs = self.element_manager.get_elements_by_attribute('kind', ComponentKind.CLEF)
        clefs_in_staff = [clef for clef in clefs if clef.get_data('staff_index') == staff_index]
        clef = self.element_manager.get_previous_element_by_time(time + 0.01, sorted(clefs_in_staff))
        if not staff:
            return None
        line_count = staff.get_data('line_count')
        clef_step = clef.get_data('step')
        clef_octave = clef.get_data('octave')
        clef_line_number = clef.get_data('line_number')

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

        return (lower_step, clef_octave + lower_step_octave_diff), (upper_step % 7, clef_octave + upper_step_octave_diff)

    def update_height(self):
        self.scene.set_height(self.STAFF_VERTICAL_AREA * self.get_data('staff_count'))
        self.view.set_height(self.STAFF_VERTICAL_AREA * self.get_data('staff_count'))

    def on_score_timeline_components_deserialized(self, id: int):
        if id != self.id:
            return

        def element_needs_update(e):
            return e.kind in [ComponentKind.NOTE, ComponentKind.KEY_SIGNATURE]

        needs_update = self.element_manager.get_elements_by_condition(element_needs_update)
        for element in needs_update:
            element.on_components_deserialized()

    def average_measure_width(self) -> float:
        if self._measure_count == 0:
            return 0
        bar_lines = sorted(self.element_manager.get_elements_by_attribute('kind', ComponentKind.BAR_LINE))
        x0 = get_x_by_time(bar_lines[0].get_data('time'))
        x1 = get_x_by_time(bar_lines[-1].get_data('time'))
        return (x1 - x0) / self._measure_count
