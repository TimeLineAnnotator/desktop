from __future__ import annotations

import copy
from collections import defaultdict

import tilia.errors
from tilia.requests import Get, Post, get, listen, post
from tilia.timelines.beat.pattern import parse
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.timelines.beat.units import MeasureMeter, format_units
from tilia.timelines.component_kinds import ComponentKind
from tilia.ui import commands
from tilia.ui.coords import time_x_converter
from tilia.ui.format import format_numerator
from tilia.ui.menus import BeatMenu
from tilia.ui.strings import (
    BEAT_PATTERN_OVERWRITE_PROMPT,
    BEAT_PATTERN_OVERWRITE_TITLE,
    BEAT_TIMELINE_DELETE_EXISTING_BEATS_PROMPT,
    BEAT_TIMELINE_FILL_TITLE,
    BEAT_UNIT_AMBIGUOUS_TOOLTIP,
    BEAT_UNIT_ASSUMED_TOOLTIP,
    BEAT_UNIT_CONFLICT_TOOLTIP,
)
from tilia.ui.timelines.base.timeline import TimelineUI, with_elements
from tilia.ui.timelines.beat.beat_unit import BeatUnitUI
from tilia.ui.timelines.beat.context_menu import BeatTimelineUIContextMenu
from tilia.ui.timelines.beat.element import BeatUI
from tilia.ui.timelines.beat.time_signature import (
    LabelState,
    TimeSignatureLabel,
    TimeSignatureLabelSpec,
)
from tilia.ui.timelines.beat.toolbar import BeatTimelineToolbar
from tilia.ui.timelines.beat_time_signatures import (
    get_creation_args,
    set_time_signatures_shown,
)
from tilia.ui.timelines.collection.collection import (
    TimelineSelector,
    TimelineUIs,
    command_callback,
)
from tilia.ui.timelines.copy_paste import (
    get_copy_data_from_element,
)
from tilia.ui.timelines.time_signature_glyphs import load_time_signature_pixmaps


class BeatTimelineUI(TimelineUI):
    CONTEXT_MENU_CLASS = BeatTimelineUIContextMenu
    TOOLBAR_CLASS = BeatTimelineToolbar
    ELEMENT_CLASS = [BeatUI, BeatUnitUI]
    ACCEPTS_HORIZONTAL_ARROWS = True
    UPDATE_TRIGGERS = TimelineUI.UPDATE_TRIGGERS + [
        "beat_pattern",
        "measure_numbers",
        "beats_that_start_measures",
        "measures_to_force_display",
        "beats_in_measure",
        "show_time_signatures",
    ]
    timeline_class = BeatTimeline
    menu_class = BeatMenu

    def __init__(self, *args, **kwargs):
        # Time signatures governed by no beat unit (the default) belong to
        # no element, so they are kept here.
        self._default_time_signature_labels: list[TimeSignatureLabel] = []
        self._time_signature_pixmaps = None
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

        commands.register(
            "timeline.beat.set_pattern", cls.on_set_pattern, text="Set beat pattern"
        )

        cls.register_timeline_command(
            collection,
            "set_beat_unit",
            cls.on_set_beat_unit,
            TimelineSelector.SELECTED,
            text="Set beat unit",
        )

        cls.register_timeline_command(
            collection,
            "remove_other_beat_units",
            cls.on_remove_other_beat_units,
            TimelineSelector.SELECTED,
            text="Remove other beat units in this measure",
        )

        commands.register(
            "timeline.beat.toggle_time_signatures",
            cls.on_toggle_time_signatures,
            text="Show or hide time signatures",
        )

    @property
    def beat_uis(self) -> list[BeatUI]:
        return [e for e in self.elements if isinstance(e, BeatUI)]

    @property
    def beat_unit_uis(self) -> list[BeatUnitUI]:
        return [e for e in self.elements if isinstance(e, BeatUnitUI)]

    # Beat unit elements are only reachable through their labels; iterating,
    # indexing and counting the timeline UI concern its beats.
    def __iter__(self):
        return iter(self.beat_uis)

    def __getitem__(self, item):
        return self.beat_uis[item]

    def __len__(self):
        return len(self.beat_uis)

    def get_next_element(self, element):
        beat_uis = self.beat_uis
        if element not in beat_uis:
            return None
        index = beat_uis.index(element)
        return beat_uis[index + 1] if index + 1 < len(beat_uis) else None

    def get_previous_element(self, element):
        beat_uis = self.beat_uis
        if element not in beat_uis:
            return None
        index = beat_uis.index(element)
        return beat_uis[index - 1] if index > 0 else None

    def on_horizontal_arrow_press(self, arrow: str):
        if any(isinstance(e, BeatUnitUI) for e in self.selected_elements):
            return
        super().on_horizontal_arrow_press(arrow)

    @property
    def time_signature_pixmaps(self) -> dict:
        if self._time_signature_pixmaps is None:
            self._time_signature_pixmaps = load_time_signature_pixmaps()
        return self._time_signature_pixmaps

    @property
    def beat_bottom_y(self) -> float:
        return BeatUI.HEIGHT_TALL

    def on_timeline_component_created(self, kind, id, get_data, set_data):
        element = super().on_timeline_component_created(kind, id, get_data, set_data)
        if kind == ComponentKind.BEAT_UNIT:
            self.update_time_signatures()
        return element

    def on_timeline_component_deleted(self, id: int):
        was_beat_unit = isinstance(self.id_to_element.get(id), BeatUnitUI)
        super().on_timeline_component_deleted(id)
        if was_beat_unit:
            self.update_time_signatures()

    def update_time_on_elements(self) -> None:
        super().update_time_on_elements()
        # Time signature labels belong to no element, or to beat unit
        # elements that are positioned from here, so they are redrawn once.
        self.update_time_signatures()

    @staticmethod
    def _get_label_state(meter: MeasureMeter) -> LabelState:
        if meter.is_conflicting:
            return LabelState.CONFLICTING
        if meter.is_ambiguous:
            return LabelState.AMBIGUOUS
        return LabelState.NORMAL

    @staticmethod
    def _get_label_tooltip(meter: MeasureMeter) -> str:
        lines = []
        if meter.is_conflicting:
            lines.append(BEAT_UNIT_CONFLICT_TOOLTIP)
        elif meter.is_ambiguous:
            lines.append(
                BEAT_UNIT_AMBIGUOUS_TOOLTIP.format(
                    len(meter.beat_values),
                    format_units(meter.units),
                    format_units(meter.beat_values),
                )
            )
        if meter.is_assumed:
            lines.append(BEAT_UNIT_ASSUMED_TOOLTIP)
        return "\n".join(lines)

    def get_time_signature_label_specs(
        self,
    ) -> dict[int | str | None, list[TimeSignatureLabelSpec]]:
        """
        Labels to show, by the id of the beat unit that governs them (None
        for the default). A label is shown where the time signature changes,
        where a beat unit starts, and where a measure needs attention.
        """
        specs = defaultdict(list)
        if not self.get_data("show_time_signatures"):
            return specs

        timeline = self.timeline
        beats = timeline.components
        starts = getattr(timeline, "beats_that_start_measures", [])
        previous = None
        for measure_index, meter in enumerate(timeline.measure_meters):
            if measure_index >= len(starts) or starts[measure_index] >= len(beats):
                break
            state = self._get_label_state(meter)
            if (
                meter.time_signature != previous
                or meter.starts_here
                or state != LabelState.NORMAL
            ):
                specs[meter.beat_unit_id].append(
                    TimeSignatureLabelSpec(
                        measure_index=measure_index,
                        x=time_x_converter.get_x_by_time(
                            beats[starts[measure_index]].time
                        ),
                        numerator=format_numerator(meter.numerator),
                        denominator=str(meter.denominator),
                        state=state,
                        tooltip=self._get_label_tooltip(meter),
                        assumed=meter.is_assumed,
                    )
                )
            previous = meter.time_signature
        return specs

    def update_time_signatures(self) -> None:
        specs = self.get_time_signature_label_specs()
        for beat_unit_ui in self.beat_unit_uis:
            beat_unit_ui.set_labels(specs.get(beat_unit_ui.id, []))

        for label in self._default_time_signature_labels:
            self.scene.removeItem(label.body)
            self.scene.removeItem(label)
        self._default_time_signature_labels = []
        for spec in specs.get(None, []):
            label = TimeSignatureLabel(spec, self.time_signature_pixmaps)
            self.scene.addItem(label.body)
            self.scene.addItem(label)
            self._default_time_signature_labels.append(label)

    @property
    def default_time_signature_labels(self) -> list[TimeSignatureLabel]:
        return list(self._default_time_signature_labels)

    @staticmethod
    def on_inspector_field_edited(
        element, field_name: str, value, inspected_id: int, inspector_id: int
    ) -> None:
        if isinstance(element, BeatUnitUI):
            if inspected_id == element.id:
                element.on_inspector_edit(field_name, value)
            return
        TimelineUI.on_inspector_field_edited(
            element, field_name, value, inspected_id, inspector_id
        )

    def update_show_time_signatures(self) -> None:
        self.update_time_signatures()

    @staticmethod
    @command_callback
    def on_toggle_time_signatures(timeline_ui: BeatTimelineUI) -> bool:
        return set_time_signatures_shown(
            timeline_ui.id, not timeline_ui.get_data("show_time_signatures")
        )

    def _get_beat_unit_target_measure(self) -> int | None:
        """
        The measure a beat unit command applies to: the one whose label was
        clicked, or else the measure of the first selected beat.
        """
        for element in self.selected_elements:
            if (
                isinstance(element, BeatUnitUI)
                and element.active_measure_index is not None
            ):
                return element.active_measure_index
        beat_uis = [e for e in self.selected_elements if isinstance(e, BeatUI)]
        if beat_uis:
            return self._get_measure_indices(beat_uis)[0]
        return None

    def on_set_beat_unit(
        self,
        measure_index: int | None = None,
        denominator: int | None = None,
        units: str | None = None,
        only_this_measure: bool | None = None,
    ) -> bool:
        timeline = self.timeline
        if measure_index is None:
            measure_index = self._get_beat_unit_target_measure()
        if measure_index is None or not 0 <= measure_index < timeline.measure_count:
            return False

        if denominator is None or units is None:
            meter = timeline.get_measure_meter(measure_index)
            next_index = measure_index + 1
            # Both scopes do the same when the next measure starts its own
            # beat unit, or there is none.
            show_scope = (
                next_index < timeline.measure_count
                and not timeline.get_measure_meter(next_index).starts_here
            )
            accepted, result = get(
                Get.FROM_USER_BEAT_UNIT,
                meter.denominator,
                format_units(meter.units),
                timeline.beats_in_measure[measure_index],
                show_scope,
            )
            if not accepted:
                return False
            denominator, units = result.denominator, result.units
            if only_this_measure is None:
                only_this_measure = result.only_this_measure

        return timeline.set_beat_unit(
            measure_index, denominator, units, bool(only_this_measure)
        )

    def on_remove_other_beat_units(self, measure_index: int | None = None) -> bool:
        """
        Keeps only the beat unit that applies in a measure holding several,
        i.e. the first one.
        """
        if measure_index is None:
            measure_index = self._get_beat_unit_target_measure()
        if measure_index is None:
            return False

        others = self.timeline.get_beat_units_in_measure(measure_index)[1:]
        if not others:
            return False
        self.timeline.delete_components(others)
        return True

    def _get_measure_indices(self, elements: list[BeatUI]):
        measure_indices = set()
        for e in elements:
            beat_index = self.timeline.get_beat_index(self.timeline.get_component(e.id))
            measure_index, _ = self.timeline.get_measure_index(beat_index)
            measure_indices.add(measure_index)

        return sorted(list(measure_indices))

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

    @staticmethod
    @command_callback
    def on_set_pattern(
        timeline_ui: "BeatTimelineUI", pattern: str | None = None
    ) -> bool:
        timeline = timeline_ui.timeline
        if pattern is None:
            accepted, pattern = get(
                Get.FROM_USER_BEAT_PATTERN,
                timeline.beat_pattern,
                len(timeline),
                timeline.get_bars_overwritten_by,
            )
            if not accepted:
                return False

        result = parse(pattern)
        if not result.is_complete:
            tilia.errors.display(tilia.errors.INVALID_BEAT_PATTERN, result.error)
            return False

        overwritten = timeline.get_bars_overwritten_by(result.bars)
        if overwritten and not get(
            Get.FROM_USER_YES_OR_NO,
            BEAT_PATTERN_OVERWRITE_TITLE,
            BEAT_PATTERN_OVERWRITE_PROMPT.format(
                ", ".join(str(i + 1) for i in overwritten)
            ),
        ):
            return False

        return timeline.set_beat_pattern(pattern)

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
        self.update_time_signatures()

    @classmethod
    def get_additional_args_for_creation(cls, beat_pattern: str | None = None):
        if beat_pattern is None:
            success, beat_pattern = get(Get.FROM_USER_BEAT_PATTERN)
            if not success:
                return False, {}
        else:
            result = parse(beat_pattern)
            if not result.is_complete:
                tilia.errors.display(tilia.errors.INVALID_BEAT_PATTERN, result.error)
                return False, {}
        return True, {"beat_pattern": beat_pattern} | get_creation_args()

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
        self.update_time_signatures()

    def get_copy_data_from_selected_elements(self):
        return self.get_copy_data_from_beat_uis(
            [e for e in self.selected_elements if isinstance(e, BeatUI)]
        )

    def get_copy_data_from_beat_uis(self, beat_uis: list[BeatUI]):
        copy_data = []
        for ui in beat_uis:
            copy_data.append(self.get_copy_data_from_beat_ui(ui))

        return copy_data

    def get_copy_data_from_beat_ui(self, beat_ui: BeatUI):
        data = get_copy_data_from_element(beat_ui, BeatUI.DEFAULT_COPY_ATTRIBUTES)
        beat_unit = self.timeline.get_beat_unit_on_beat(beat_ui.id)
        if beat_unit:
            data["beat_unit"] = {
                "denominator": beat_unit.denominator,
                "units": beat_unit.units,
                "assumed": beat_unit.assumed,
            }
        return data

    @with_elements
    def on_copy_element(self, elements) -> bool:
        # Beat units are copied along with the beats they are on.
        component_data = self.get_copy_data_from_beat_uis(
            [e for e in elements if isinstance(e, BeatUI)]
        )
        if not component_data:
            return False

        post(
            Post.TIMELINE_ELEMENT_COPY_DONE,
            {"components": component_data, "timeline_type": self.timeline_class},
        )
        return True

    def paste_single_into_timeline(self, paste_data: list[dict] | dict):
        return self.paste_multiple_into_timeline(paste_data)

    def paste_multiple_into_timeline(self, paste_data: list[dict] | dict):
        reference_time = min(md["context"]["time"] for md in paste_data)

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
            beat_time = beat_data["context"].pop("time")
            beat_unit_data = beat_data.pop("beat_unit", None)

            beat, _ = self.timeline.create_component(
                ComponentKind.BEAT,
                target_time + (beat_time - reference_time),
                **beat_data["values"],
                **beat_data["context"],
            )
            if beat and beat_unit_data:
                # A pasted first beat already has a beat unit of its own.
                self.timeline.put_beat_unit_on_beat(beat.id, **beat_unit_data)

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
        self.update_time_signatures()

    def beats_that_start_measures(self):
        for beat_ui in self:
            beat_ui.update_is_first_in_measure()
