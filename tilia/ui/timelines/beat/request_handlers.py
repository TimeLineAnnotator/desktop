from __future__ import annotations

from typing import TYPE_CHECKING

from tilia.requests import Post, get, Get
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.timelines.base.request_handlers import ElementRequestHandler
from tilia.ui.timelines.copy_paste import get_copy_data_from_element
from tilia.ui.timelines.beat import BeatUI


if TYPE_CHECKING:
    from tilia.ui.timelines.beat import BeatTimelineUI


class BeatUIRequestHandler(ElementRequestHandler):
    def __init__(self, timeline_ui: BeatTimelineUI):
        super().__init__(
            timeline_ui,
            {
                Post.BEAT_ADD: self.on_add,
                Post.BEAT_DELETE: self.on_delete,
                Post.BEAT_SET_MEASURE_NUMBER: self.on_set_measure_number,
                Post.BEAT_RESET_MEASURE_NUMBER: self.on_reset_measure_number,
                Post.BEAT_DISTRIBUTE: self.on_distribute,
                Post.BEAT_SET_AMOUNT_IN_MEASURE: self.on_set_amount_in_measure,
                Post.TIMELINE_ELEMENT_DELETE: self.on_delete,
                Post.TIMELINE_ELEMENT_COPY: self.on_copy,
                Post.TIMELINE_ELEMENT_PASTE: self.on_paste,
            },
        )

    def on_add(self, *_, **__):
        self.timeline_ui: BeatTimelineUI
        self.timeline.create_component(
            ComponentKind.BEAT, get(Get.SELECTED_TIME)
        )
        self.timeline.recalculate_measures()

    def on_delete(self, elements, *_, **__):
        self.timeline.delete_components(
            [self.timeline.get_component(e.id) for e in elements]
        )
        self.timeline.recalculate_measures()

    def _get_measure_indices(self, elements):
        measure_indices = set()
        for e in elements:
            beat_index = self.timeline.get_beat_index(self.timeline.get_component(e.id))
            measure_index, _ = self.timeline.get_measure_index(beat_index)
            measure_indices.add(measure_index)

        return sorted(list(measure_indices))

    def on_set_measure_number(self, elements, number):
        for i in reversed(self._get_measure_indices(elements)):
            self.timeline.set_measure_number(i, number)

    def on_reset_measure_number(self, elements):
        for i in reversed(self._get_measure_indices(elements)):
            self.timeline.reset_measure_number(i)

    def on_distribute(self, elements):
        for i in self._get_measure_indices(elements):
            self.timeline.distribute_beats(i)

    def on_set_amount_in_measure(self, elements, amount):
        for i in reversed(self._get_measure_indices(elements)):
            self.timeline.set_beat_amount_in_measure(i, amount)

    @staticmethod
    def on_copy(elements):
        copy_data = []
        for elm in elements:
            copy_data.append(
                {
                    "components": get_copy_data_from_element(
                        elm, BeatUI.DEFAULT_COPY_ATTRIBUTES
                    ),
                    "timeline_kind": TimelineKind.BEAT_TIMELINE,
                }
            )

        return copy_data
