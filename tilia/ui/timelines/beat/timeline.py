import copy

from tilia.requests import Get, Post, get, listen
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui import commands
from tilia.ui.strings import (
    BEAT_TIMELINE_DELETE_EXISTING_BEATS_PROMPT,
    BEAT_TIMELINE_FILL_TITLE,
)
from tilia.ui.timelines.base.timeline import TimelineUI, with_elements
from tilia.ui.timelines.beat.context_menu import BeatTimelineUIContextMenu
from tilia.ui.timelines.beat.element import BeatUI
from tilia.ui.timelines.beat.toolbar import BeatTimelineToolbar
from tilia.ui.timelines.collection.collection import (
    TimelineSelector,
    TimelineUIs,
    command_callback,
)
from tilia.ui.timelines.copy_paste import (
    get_copy_data_from_element,
)


class BeatTimelineUI(TimelineUI):
    CONTEXT_MENU_CLASS = BeatTimelineUIContextMenu
    TOOLBAR_CLASS = BeatTimelineToolbar
    ELEMENT_CLASS = BeatUI
    ACCEPTS_HORIZONTAL_ARROWS = True
    TIMELINE_KIND = TimelineKind.BEAT_TIMELINE
    UPDATE_TRIGGERS = TimelineUI.UPDATE_TRIGGERS + [
        "beat_pattern",
        "measure_numbers",
        "beats_that_start_measures",
        "measures_to_force_display",
        "beats_in_measure",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        listen(
            self,
            Post.SETTINGS_UPDATED,
            self.on_settings_updated,
        )

    @classmethod
    def register_commands(cls, collection: TimelineUIs):
        commands.register(
            "timeline.beat.fill", cls.on_beat_timeline_fill, "&Fill with beats"
        )

        cls.register_timeline_command(
            collection,
            "add",
            cls.on_add,
            TimelineSelector.FIRST,
            text="Add beat at current position",
            shortcut="b",
            icon="beat-add",
        )

        cls.register_timeline_command(
            collection,
            "set_measure_number",
            cls.on_set_measure_number,
            TimelineSelector.SELECTED,
            text="Set measure number",
            icon="beat-number-set",
        )

        cls.register_timeline_command(
            collection,
            "reset_measure_number",
            cls.on_reset_measure_number,
            TimelineSelector.SELECTED,
            text="Reset measure number",
            icon="beat-number-reset",
        )

        cls.register_timeline_command(
            collection,
            "distribute",
            cls.on_distribute,
            TimelineSelector.SELECTED,
            text="Distribute",
            icon="beat-distribute",
        )

        cls.register_timeline_command(
            collection,
            "set_amount_in_measure",
            cls.on_set_amount_in_measure,
            TimelineSelector.SELECTED,
            text="Set amount in measure",
        )

    def _get_measure_indices(self, elements: list[BeatUI]):
        measure_indices = set()
        for e in elements:
            beat_index = self.timeline.get_beat_index(self.timeline.get_component(e.id))
            measure_index, _ = self.timeline.get_measure_index(beat_index)
            measure_indices.add(measure_index)

        return sorted(list(measure_indices))

    def on_delete_component(self, elements: list[BeatUI] | None = None) -> bool:
        success = super().on_delete_component(elements)
        if success:
            self.timeline.recalculate_measures()
        return success

    @with_elements
    def on_set_measure_number(self, elements: list[BeatUI] | None = None):
        accepted, number = get(
            Get.FROM_USER_INT,
            "Change measure number",
            "Insert measure number",
            minValue=0,
        )
        if not accepted:
            return False

        for i in reversed(self._get_measure_indices(elements)):
            self.timeline.set_measure_number(i, number)
        return True

    @with_elements
    def on_reset_measure_number(self, elements: list[BeatUI] | None = None):
        for i in reversed(self._get_measure_indices(elements)):
            self.timeline.reset_measure_number(i)
        return True

    @with_elements
    def on_distribute(self, elements: list[BeatUI] | None = None):
        for i in self._get_measure_indices(elements):
            self.timeline.distribute_beats(i)
        return True

    @with_elements
    def on_set_amount_in_measure(self, elements: list[BeatUI] | None = None):
        accepted, amount = get(
            Get.FROM_USER_INT,
            "Change beats in measure",
            "Insert amount of beats in measure",
            minValue=1,
        )
        if not accepted:
            return False
        for i in reversed(self._get_measure_indices(elements)):
            self.timeline.set_beat_amount_in_measure(i, amount)
        return True

    def on_add(self, time: float | None = None):
        if time is None:
            time = get(Get.SELECTED_TIME)

        self.timeline_ui: BeatTimelineUI
        component, _ = self.timeline.create_component(ComponentKind.BEAT, time)
        self.timeline.recalculate_measures()
        return False if component is None else True

    @staticmethod
    @command_callback
    def on_beat_timeline_fill():
        accepted, result = get(Get.FROM_USER_BEAT_TIMELINE_FILL_METHOD)
        if not accepted:
            return False

        timeline, method, value = result

        if not timeline.is_empty:
            confirmed = get(
                Get.FROM_USER_YES_OR_NO,
                BEAT_TIMELINE_FILL_TITLE,
                BEAT_TIMELINE_DELETE_EXISTING_BEATS_PROMPT,
            )
            if not confirmed:
                return False
            timeline.clear()

        timeline.fill_with_beats(method, value)

        return True

    def on_timeline_components_deserialized(self):
        for beat_ui in self:
            beat_ui.update_label()

    @classmethod
    def get_additional_args_for_creation(cls):
        success, beat_pattern = get(Get.FROM_USER_BEAT_PATTERN)
        return success, {"beat_pattern": beat_pattern}

    def on_settings_updated(self, updated_settings):
        if "beat_timeline" in updated_settings:
            for beat_ui in self:
                beat_ui.update_label()

    def _deselect_all_but_last(self):
        if len(self.selected_elements) > 1:
            for element in self.selected_elements[:-1]:
                self.element_manager.deselect_element(element)

    def _deselect_all_but_first(self):
        if len(self.selected_elements) > 1:
            for element in self.selected_elements[1:]:
                self.element_manager.deselect_element(element)

    def should_display_measure_number(self, beat_ui):
        beat = self.timeline.get_component(beat_ui.id)
        beat_index = self.timeline.components.index(beat)
        measure_index, _ = self.timeline.get_measure_index(beat_index)
        return self.timeline.should_display_measure_number(measure_index)

    def on_measure_number_change_done(self, start_index: int):
        for beat_ui in self[start_index:]:
            beat_ui.update_label()

    def get_copy_data_from_selected_elements(self):
        return self.get_copy_data_from_beat_uis(self.selected_elements)

    def get_copy_data_from_beat_uis(self, beat_uis: list[BeatUI]):
        copy_data = []
        for ui in beat_uis:
            copy_data.append(self.get_copy_data_from_beat_ui(ui))

        return copy_data

    @staticmethod
    def get_copy_data_from_beat_ui(beat_ui: BeatUI):
        return get_copy_data_from_element(beat_ui, BeatUI.DEFAULT_COPY_ATTRIBUTES)

    def paste_single_into_timeline(self, paste_data: list[dict] | dict):
        return self.paste_multiple_into_timeline(paste_data)

    def paste_multiple_into_timeline(self, paste_data: list[dict] | dict):
        reference_time = min(
            md["support_by_component_value"]["time"] for md in paste_data
        )

        self.create_pasted_beats(
            paste_data,
            reference_time,
            get(Get.MEDIA_CURRENT_TIME),
        )

    def create_pasted_beats(
        self, paste_data: list[dict], reference_time: float, target_time: float
    ) -> None:
        for beat_data in copy.deepcopy(
            paste_data
        ):  # deepcopying so popping won't affect original data
            beat_time = beat_data["support_by_component_value"].pop("time")

            self.timeline.create_component(
                ComponentKind.BEAT,
                target_time + (beat_time - reference_time),
                **beat_data["by_component_value"],
                **beat_data["support_by_component_value"],
            )

    def update_beat_pattern(self):
        pass  # not implemented

    def update_measure_numbers(self):
        for beat_ui in self:
            try:
                beat_ui.update_label()
            except IndexError:
                # State is being restored and
                # beats in measure has not been
                # updated yet. This is a dangerous
                # workaround, as it might conceal
                # other exceptions. Let's fix this ASAP.
                continue

    def update_measures_to_force_display(self):
        for beat_ui in self:
            beat_ui.update_label()

    def update_beats_in_measure(self):
        for beat_ui in self:
            beat_ui.update_is_first_in_measure()

    def beats_that_start_measures(self):
        for beat_ui in self:
            beat_ui.update_is_first_in_measure()
