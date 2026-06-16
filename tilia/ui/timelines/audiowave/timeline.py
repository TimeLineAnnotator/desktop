from __future__ import annotations

from tilia.requests import Get, Post, get, listen
from tilia.timelines.audiowave.timeline import AudioWaveTimeline
from tilia.ui.timelines.audiowave.element import AmplitudeBarUI
from tilia.ui.timelines.base.timeline import TimelineUI

from ...format import format_media_time


class AudioWaveTimelineUI(TimelineUI):
    ELEMENT_CLASS = AmplitudeBarUI
    ACCEPTS_HORIZONTAL_ARROWS = True
    timeline_class = AudioWaveTimeline

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_requests()

    def _setup_requests(self):
        listen(self, Post.PLAYER_URL_CHANGED, lambda _: self.timeline.refresh())
        listen(
            self,
            Post.SETTINGS_UPDATED,
            self.on_settings_updated,
        )

    def on_settings_updated(self, updated_settings):
        if "audiowave_timeline" in updated_settings:
            get(Get.TIMELINE_COLLECTION).set_timeline_data(
                self.id, "height", self.timeline.default_height
            )
            self.timeline.refresh()

    def on_horizontal_arrow_press(self, arrow: str):
        if not self.has_selected_elements:
            return

        if arrow not in ["right", "left"]:
            raise ValueError(f"Invalid arrow '{arrow}'.")

        if arrow == "right":
            self._deselect_all_but_last()
        else:
            self._deselect_all_but_first()

        selected_element = self.element_manager.get_selected_elements()[0]
        if arrow == "right":
            element_to_select = self.element_manager.get_next_element(selected_element)
        else:
            element_to_select = self.element_manager.get_previous_element(
                selected_element
            )

        if element_to_select:
            self.deselect_element(selected_element)
            self.select_element(element_to_select)

    def get_inspector_dict(self):
        start_time = self.selected_elements[0].get_data("start")
        end_time = self.selected_elements[-1].get_data("end")
        a_sum = sum([e.get_data("amplitude") for e in self.selected_elements])
        amplitude = f"{a_sum / len(self.selected_elements): .3f} (rms)"

        return {
            "Start / End": f"{format_media_time(start_time)} /"
            + f"{format_media_time(end_time)}",
            "Amplitude": amplitude,
        }
