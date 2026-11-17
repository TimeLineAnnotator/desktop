from __future__ import annotations

import copy
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsItem

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
    BEAT_TIMELINE_DELETE_EXISTING_BEATS_PROMPT,
    BEAT_TIMELINE_FILL_TITLE,
    BEAT_UNIT_AMBIGUOUS_TOOLTIP,
    BEAT_UNIT_ASSUMED_TOOLTIP,
    BEAT_UNIT_CONFLICT_TOOLTIP,
)
from tilia.ui.timelines.base.element import TimelineUIElement
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
        "show_time_signatures",
    ]
    timeline_class = BeatTimeline
    menu_class = BeatMenu

    def __init__(self, *args, **kwargs):
        # Time signatures governed by no beat unit (the default) belong to
        # no element, so they are kept here.
        self._default_time_signature_labels: list[TimeSignatureLabel] = []
        # The beat unit each item of a time signature label belongs to, or
        # None for the glyphs, which belong to no element, so a selection box
        # finds it at once rather than by asking every element whether the
        # item is one of its (see `get_item_owner`).
        self.label_item_owners: dict[QGraphicsItem, BeatUnitUI | None] = {}
        # The selected time signature labels, as the first beats of their
        # bars, with the bars' positions, and the one clicked last. Kept here
        # rather than by the beat units the labels belong to, so a selected
        # label follows its bar to whichever beat unit has it after a change
        # (see `_keep_label_selection`).
        self.selected_label_bars: dict[int | str, int] = {}
        self.clicked_label_bar: int | str | None = None
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
            "timeline.beat.set_pattern",
            cls.on_set_pattern,
            text="Edit bars and time signatures",
        )

        cls.register_timeline_command(
            collection,
            "edit_bars",
            cls.on_edit_bars,
            TimelineSelector.SELECTED,
            text="Edit bars and time signatures",
        )

        cls.register_timeline_command(
            collection,
            "remove_other_beat_units",
            cls.on_remove_other_beat_units,
            TimelineSelector.SELECTED,
            text="Keep only the first time signature in this measure",
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
    def __iter__(self) -> Iterator[BeatUI]:
        return iter(self.beat_uis)

    def __getitem__(self, item: int | slice) -> BeatUI | list[BeatUI]:
        return self.beat_uis[item]

    def __len__(self) -> int:
        return len(self.beat_uis)

    def get_next_element(self, element: TimelineUIElement) -> BeatUI | None:
        beat_uis = self.beat_uis
        if element not in beat_uis:
            return None
        index = beat_uis.index(element)
        return beat_uis[index + 1] if index + 1 < len(beat_uis) else None

    def get_previous_element(self, element: TimelineUIElement) -> BeatUI | None:
        beat_uis = self.beat_uis
        if element not in beat_uis:
            return None
        index = beat_uis.index(element)
        return beat_uis[index - 1] if index > 0 else None

    def on_horizontal_arrow_press(self, arrow: str) -> None:
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

    def on_timeline_component_created(
        self,
        kind: ComponentKind,
        id: int,
        get_data: Callable[[str], Any],
        set_data: Callable[[str, Any], None],
    ) -> TimelineUIElement:
        element = super().on_timeline_component_created(kind, id, get_data, set_data)
        if kind == ComponentKind.BEAT_UNIT:
            self.update_time_signatures()
        return element

    def on_timeline_component_deleted(self, id: int) -> None:
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
        Labels to show, by the id of the beat that carries the beat unit
        governing them (None where no unit set on a beat does). A label is
        shown where the time signature changes, where a beat unit starts, and
        where a measure needs attention.
        """
        specs = defaultdict(list)
        if not self.get_data("show_time_signatures"):
            return specs

        timeline = self.timeline
        beats = timeline.components
        starts = timeline.beats_that_start_measures
        previous = None
        for measure_index, meter in enumerate(timeline.measure_meters):
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
        if self.timeline.component_manager.is_bulk:
            # Redrawn once the bulk change is done.
            return
        specs = self.get_time_signature_label_specs()
        for beat_unit_ui in self.beat_unit_uis:
            beat_unit_ui.set_labels(specs.get(beat_unit_ui.get_data("beat_id"), []))
        self._keep_label_selection()

        for label in self._default_time_signature_labels:
            self.scene.removeItem(label.body)
            self.scene.removeItem(label)
        self._default_time_signature_labels = []
        for spec in specs.get(None, []):
            label = TimeSignatureLabel(spec, self.time_signature_pixmaps)
            self.scene.addItem(label.body)
            self.scene.addItem(label)
            self._default_time_signature_labels.append(label)

    def add_selected_label_bar(
        self, beat_id: int | str, measure_index: int, clicked: bool
    ) -> None:
        self.selected_label_bars[beat_id] = measure_index
        if clicked:
            self.clicked_label_bar = beat_id

    def remove_selected_label_bars(self, beat_ids: Iterable[int | str]) -> None:
        for beat_id in beat_ids:
            self.selected_label_bars.pop(beat_id, None)
            if beat_id == self.clicked_label_bar:
                self.clicked_label_bar = None

    def _keep_label_selection(self) -> None:
        """
        Once the labels are drawn again, gives each selected bar to the beat
        unit whose label it has now, which a change can make another one: a
        time signature set on the bar, the one written back after it, or a
        beat unit made again on the bar's new first beat. A bar is followed
        by the beat that starts it, so it follows the barlines; if that beat
        is gone or starts no bar any more, by its position, which a bar keeps
        when its first beat is deleted (see `BeatTimeline._remeasure`). A bar
        whose label is gone is dropped, and a beat unit left with no selected
        label is deselected, so Delete acts only on labels someone chose. The
        beat unit that has the label clicked last is given to the inspector.
        """
        timeline = self.timeline
        starts = timeline.beats_that_start_measures
        beat_unit_uis = self.beat_unit_uis
        owners = {
            measure_index: beat_unit_ui
            for beat_unit_ui in beat_unit_uis
            for measure_index in beat_unit_ui.label_measure_indices
        }
        old_clicked_owner = next(
            (u for u in beat_unit_uis if u.has_selected_label(self.clicked_label_bar)),
            None,
        )

        selection: dict[int | str, int] = {}
        clicked = None
        for beat_id, old_index in self.selected_label_bars.items():
            measure_index = timeline.get_measure_started_by(beat_id)
            new_beat_id = beat_id
            if measure_index is None and old_index < len(starts):
                measure_index = old_index
                new_beat_id = timeline[starts[old_index]].id
            if measure_index not in owners:
                continue
            selection[new_beat_id] = measure_index
            if beat_id == self.clicked_label_bar:
                clicked = new_beat_id
        self.selected_label_bars = selection
        self.clicked_label_bar = clicked

        shares: dict[BeatUnitUI, dict[int | str, int]] = defaultdict(dict)
        for beat_id, measure_index in selection.items():
            shares[owners[measure_index]][beat_id] = measure_index
        # Whether the inspector was given another beat unit, or lost one.
        inspector_changed = False
        for beat_unit_ui in beat_unit_uis:
            share = shares.get(beat_unit_ui, {})
            had_labels = beat_unit_ui.has_selected_labels
            if beat_unit_ui.set_selected_labels(share):
                inspector_changed = True
            if share and not beat_unit_ui.is_selected():
                self.select_element(beat_unit_ui)
                inspector_changed = True
            elif beat_unit_ui.is_selected() and had_labels and not share:
                self.deselect_element(beat_unit_ui)
                inspector_changed = True

        # The inspector shows the beat unit given to it last, which is to be
        # the one with the label clicked last.
        clicked_owner = owners[selection[clicked]] if clicked is not None else None
        if clicked_owner is not None and (
            inspector_changed or clicked_owner is not old_clicked_owner
        ):
            clicked_owner.refresh_inspector()

    def delete_element(self, element: TimelineUIElement) -> None:
        # A beat unit can go while labels are selected, as when it is made
        # again on its bar's new first beat, or undo makes it again: their
        # bars stay selected, for the beat units that have them next (see
        # `_keep_label_selection`).
        kept = dict(self.selected_label_bars), self.clicked_label_bar
        super().delete_element(element)
        if isinstance(element, BeatUnitUI):
            self.selected_label_bars, self.clicked_label_bar = kept

    @property
    def default_time_signature_labels(self) -> list[TimeSignatureLabel]:
        return list(self._default_time_signature_labels)

    @staticmethod
    def on_inspector_field_edited(
        element: TimelineUIElement,
        field_name: str,
        value: Any,
        inspected_id: int,
        inspector_id: int,
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
        The measure a time signature command applies to: the one whose label
        was clicked, or else the measure of the first selected beat.
        """
        for element in self.selected_elements:
            if not isinstance(element, BeatUnitUI):
                continue
            measure_index = element.active_measure_index
            if measure_index is not None:
                return measure_index
        beat_uis = [e for e in self.selected_elements if isinstance(e, BeatUI)]
        if beat_uis:
            return self._get_measure_indices(beat_uis)[0]
        return None

    def on_edit_bars(self, measure_index: int | None = None) -> bool:
        """
        Opens the bars and time signatures dialog at the measure of the
        clicked label or selected beat.
        """
        if measure_index is None:
            measure_index = self._get_beat_unit_target_measure()
        return self.edit_bars(measure_index)

    def edit_bars(self, measure_index: int | None = None) -> bool:
        """
        Asks for the bars in a dialog that shows them as they are and what
        changes, then remeasures the beats from it and numbers the measures.
        """
        timeline = self.timeline
        accepted, edit = get(
            Get.FROM_USER_BARS,
            timeline.beat_pattern,
            len(timeline),
            timeline.get_measures_as_planned_bars(),
            timeline.measure_numbers,
            measure_index,
            timeline.beat_pattern_shift,
        )
        if not accepted:
            return False
        return timeline.set_bars(
            edit.pattern, edit.bars, edit.numbers, edit.pattern_shift
        )

    def on_remove_other_beat_units(self, measure_index: int | None = None) -> bool:
        """
        Keeps only the beat unit that applies in a measure holding several,
        i.e. the first one.
        """
        if measure_index is None:
            measure_index = self._get_beat_unit_target_measure()
        if measure_index is None or not (
            0 <= measure_index < self.timeline.measure_count
        ):
            return False

        others = self.timeline.get_beat_units_in_measure(measure_index)[1:]
        if not others:
            return False
        self.timeline.delete_components(others)
        return True

    @with_elements
    def on_delete_component(self, elements: list[TimelineUIElement]) -> bool:
        """
        Deletes the selected beats, and removes the time signature changes
        at the measures of the selected labels, as the command line's
        `time-signatures remove` does (see
        `BeatTimeline.get_time_signature_change`): a label that differs from
        the one before only because its measure has other taps marks none,
        so the beat unit it shows stays. If nothing is left to delete, says
        why.
        """
        timeline = self.timeline
        to_delete = [e.tl_component for e in elements if isinstance(e, BeatUI)]
        beat_unit_ids = set()
        errors = []
        for measure_index in self._get_outlined_label_measures(elements):
            beat_unit, error = timeline.get_time_signature_change(measure_index)
            if beat_unit is None:
                errors.append((measure_index, error))
            elif beat_unit.id not in beat_unit_ids:
                beat_unit_ids.add(beat_unit.id)
                to_delete.append(beat_unit)

        if not to_delete:
            if errors:
                # The first measure's reason is about that measure alone,
                # while the others' say why a label that marks no change is
                # there, so one of those is shown first.
                errors.sort(key=lambda error: error[0] == 0)
                tilia.errors.display(
                    tilia.errors.TIME_SIGNATURE_NOT_REMOVED, errors[0][1]
                )
            return False
        # The labels of the beat units that go are deleted, not kept
        # selected for the beat units that have their bars next.
        for component in to_delete:
            if component.KIND == ComponentKind.BEAT_UNIT:
                self.deselect_element(self.get_element(component.id))
        timeline.delete_components(to_delete)
        return True

    @staticmethod
    def _get_outlined_label_measures(elements: list[TimelineUIElement]) -> list[int]:
        """
        The measures of the outlined labels of the beat units in `elements`,
        in order. A beat unit with no label, as when time signatures are
        hidden, counts as its first measure's.
        """
        measure_indices = set()
        for element in elements:
            if isinstance(element, BeatUnitUI):
                measure_indices.update(
                    element.outlined_measure_indices or [element.start_measure_index]
                )
        return sorted(measure_indices)

    def select_time_signature_label(self, measure_index: int) -> BeatUnitUI | None:
        """
        Adds a measure's time signature label to the selection, as the label
        clicked last of its beat unit, which it returns.
        """
        for beat_unit_ui in self.beat_unit_uis:
            label = beat_unit_ui.get_label(measure_index)
            if label is not None:
                if not beat_unit_ui.is_selected():
                    self.select_element(beat_unit_ui)
                beat_unit_ui.select_label(label)
                return beat_unit_ui
        return None

    def on_left_click(
        self,
        item: QGraphicsItem,
        modifier: Qt.KeyboardModifier,
        double: bool,
        x: int,
        y: int,
    ) -> None:
        # A time signature label is selected through its beat unit, but on
        # its own: Ctrl-click adds or removes that label, and the beat unit
        # is deselected once none of its labels is selected.
        beat_unit_ui = self._get_label_owner(item)
        if (
            beat_unit_ui is None
            or double
            or Qt.KeyboardModifier.ControlModifier not in modifier
        ):
            super().on_left_click(item, modifier, double, x, y)
            return

        if not beat_unit_ui.is_selected():
            self.select_element(beat_unit_ui)
            beat_unit_ui.select_label(item)
        elif not beat_unit_ui.toggle_label(item):
            self.deselect_element(beat_unit_ui)

    def on_right_click(
        self,
        x: int,
        y: int,
        item: QGraphicsItem,
        modifier: Qt.KeyboardModifier,
    ) -> None:
        # Right-clicking a label that isn't selected selects it alone, as it
        # does an element; with Shift or Ctrl, it adds it.
        beat_unit_ui = self._get_label_owner(item)
        if (
            beat_unit_ui is not None
            and modifier == Qt.KeyboardModifier.NoModifier
            and beat_unit_ui.is_selected()
            and not beat_unit_ui.is_outlined(item)
        ):
            beat_unit_ui.deselect_labels()
        super().on_right_click(x, y, item, modifier)

    def belongs_to_selection(self, item: QGraphicsItem) -> bool:
        # A label of a selected beat unit belongs to the selection only if it
        # is outlined, so right-clicking another selects that one alone.
        beat_unit_ui = self._get_label_owner(item)
        if beat_unit_ui is not None:
            return beat_unit_ui.is_selected() and beat_unit_ui.is_outlined(item)
        return super().belongs_to_selection(item)

    def _get_label_owner(self, item: QGraphicsItem | None) -> BeatUnitUI | None:
        if not isinstance(item, TimeSignatureLabel):
            return None
        return self.label_item_owners.get(item)

    def get_item_owner(self, item: QGraphicsItem) -> list[TimelineUIElement]:
        if item in self.label_item_owners:
            owner = self.label_item_owners[item]
            return [] if owner is None else [owner]
        return super().get_item_owner(item)

    def _get_measure_indices(self, elements: list[TimelineUIElement]) -> list[int]:
        """
        The measures of the beats among `elements`, in order. A selection can
        also hold time signature labels, as a box over the beats and their
        labels selects both, and those are left out.
        """
        measure_indices = set()
        for e in elements:
            if not isinstance(e, BeatUI):
                continue
            beat_index = self.timeline.get_beat_index(self.timeline.get_component(e.id))
            measure_index, _ = self.timeline.get_measure_index(beat_index)
            measure_indices.add(measure_index)

        return sorted(list(measure_indices))

    @with_elements
    def on_set_measure_number(self, elements: list[BeatUI] | None = None):
        measure_indices = self._get_measure_indices(elements)
        if not measure_indices:
            return False
        accepted, number = get(
            Get.FROM_USER_INT,
            "Change measure number",
            "Insert measure number",
            minValue=0,
        )
        if not accepted:
            return False

        for i in reversed(measure_indices):
            self.timeline.set_measure_number(i, number)
        return True

    @with_elements
    def on_reset_measure_number(self, elements: list[BeatUI] | None = None):
        measure_indices = self._get_measure_indices(elements)
        for i in reversed(measure_indices):
            self.timeline.reset_measure_number(i)
        return bool(measure_indices)

    @with_elements
    def on_distribute(self, elements: list[BeatUI] | None = None):
        measure_indices = self._get_measure_indices(elements)
        for i in measure_indices:
            self.timeline.distribute_beats(i)
        return bool(measure_indices)

    @with_elements
    def on_set_amount_in_measure(
        self, elements: list[BeatUI] | None = None, amount: int | None = None
    ) -> bool:
        measure_indices = self._get_measure_indices(elements)
        if not measure_indices:
            return False
        if amount is None:
            accepted, amount = get(
                Get.FROM_USER_INT,
                "Change beats in measure",
                "Insert amount of beats in measure",
                minValue=1,
            )
            if not accepted:
                return False
        elif amount < 1:
            return False
        for i in reversed(measure_indices):
            self.timeline.set_beat_amount_in_measure(i, amount)
        return True

    @staticmethod
    @command_callback
    def on_set_pattern(
        timeline_ui: "BeatTimelineUI",
        pattern: str | None = None,
        numbers: list[int] | None = None,
    ) -> bool:
        """
        Remeasures the beats from a pattern of time signatures and numbers
        the measures. Without a pattern, asks for both in a dialog that shows
        the bars as they are and what changes; with one, applies it, as
        editing the dialog's line does.
        """
        timeline = timeline_ui.timeline
        if pattern is None:
            return timeline_ui.edit_bars()

        result = parse(pattern)
        if not result.is_complete:
            tilia.errors.display(tilia.errors.INVALID_BEAT_PATTERN, result.error)
            return False

        if not timeline.set_beat_pattern(pattern):
            return False
        if numbers is not None:
            timeline.set_measure_numbers(numbers)
        return True

    def on_add(self, time: float | None = None):
        if time is None:
            time = get(Get.SELECTED_TIME)

        component, _ = self.timeline.create_component(ComponentKind.BEAT, time)
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
    def get_additional_args_for_creation(
        cls, beat_pattern: str | None = None
    ) -> tuple[bool, dict[str, Any]]:
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
        if self.timeline.component_manager.is_bulk:
            # Beats are relabelled once the bulk change is done.
            return False
        beat = self.timeline.get_component(beat_ui.id)
        beat_index = self.timeline.get_beat_index(beat)
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

    def get_copy_data_from_beat_ui(self, beat_ui: BeatUI) -> dict[str, Any]:
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
    def on_copy_element(self, elements: list[TimelineUIElement]) -> bool:
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
        pasted_beat_units = []
        with self.timeline.adding_beats_together():
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
                    pasted_beat_units.append((beat, beat_unit_data))
        # Once the pasted beats are in their measures, a beat brings the beat
        # unit a person set on it, and only where it starts a measure: pasted
        # inside one, it would change the time signature of that measure and
        # of every one after it. An assumed beat unit, which TiLiA gave, is
        # never pasted. A pasted first beat already has a beat unit of its
        # own, which the pasted one replaces.
        for beat, beat_unit_data in pasted_beat_units:
            if beat_unit_data.get("assumed") or not beat.is_first_in_measure:
                continue
            self.timeline.put_beat_unit_on_beat(beat.id, **beat_unit_data)

    def update_beat_pattern(self):
        pass  # not implemented
