from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGraphicsItem

from tilia.requests import Get, Post, get, listen, post
from tilia.timelines.timeline_kinds import TimelineKind
from tilia.ui.coords import time_x_converter
from tilia.ui.timelines.audiowave.element import WaveformElement
from tilia.ui.timelines.base.timeline import TimelineUI


class AudioWaveTimelineUI(TimelineUI):
    ELEMENT_CLASS = WaveformElement
    TIMELINE_KIND = TimelineKind.AUDIOWAVE_TIMELINE

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_requests()

    def _setup_requests(self):
        listen(self, Post.PLAYER_URL_CHANGED, lambda _: self.timeline.refresh())
        listen(self, Post.SETTINGS_UPDATED, self.on_settings_updated)

    def on_settings_updated(self, updated_settings):
        if "audiowave_timeline" in updated_settings:
            get(Get.TIMELINE_COLLECTION).set_timeline_data(
                self.id, "height", self.timeline.default_height
            )
            self.timeline.refresh()

    def on_left_click(
        self,
        item: QGraphicsItem,
        modifier: Qt.KeyboardModifier,
        double: bool,
        x: int,
        y: int,
    ) -> None:
        # Audacity-style: clicking anywhere on the waveform seeks playback
        # to that time.  No selection, no inspector — the waveform is read-only.
        if not self.get_item_owner(item):
            return
        post(Post.PLAYER_SEEK_IF_NOT_PLAYING, time_x_converter.get_time_by_x(x))
