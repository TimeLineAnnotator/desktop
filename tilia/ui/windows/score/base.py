"""What the two score viewers share: `ScoreView`, which draws scores with
Verovio, and `SvgViewer`, which shows the SVG scores of older files.

Each shows its timeline's score in a dock widget and moves the score
timeline's measure tracker over the part of the score it shows.
"""

from __future__ import annotations

from bisect import bisect
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QHideEvent, QShowEvent

from tilia.requests import Get, get
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.ui.windows.view_window import ViewDockWidget

if TYPE_CHECKING:
    from tilia.timelines.score.timeline import ScoreTimeline
    from tilia.ui.timelines.score.timeline import ScoreTimelineUI


def get_beat_timeline() -> BeatTimeline | None:
    """The beat timeline that places score positions in time, if it has
    measures."""
    beat_tl = get(Get.TIMELINE_COLLECTION).get_beat_timeline_for_measure_calculation()
    return beat_tl if beat_tl and beat_tl.measure_count else None


def get_times_at(beat_tl: BeatTimeline, measure: float, fraction: float) -> list[float]:
    """The times `beat_tl` plays a position at: a measure number and a
    fraction of that measure. A position before its first measure is at the
    start of the media, and one after its last measure at the end."""
    if times := beat_tl.get_time_by_measure(measure, fraction):
        return times
    if measure < min(beat_tl.measure_numbers):
        return [0]
    return [get(Get.MEDIA_DURATION)]


class ScoreViewerBase(ViewDockWidget):
    """A score viewer's dock widget, which subclasses fill with the score."""

    # Whether a score is shown, under the name `ScoreTimelineUI` asks for.
    is_svg_loaded: bool

    def __init__(self, name: str, tl_id: int, *args, **kwargs) -> None:
        super().__init__("TiLiA Score Viewer", *args, menu_title=name, **kwargs)
        self.setObjectName(f"TiLiA Score Viewer {tl_id}")
        self.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.timeline_id = tl_id
        self.is_hidden = False
        self.visible_times = [0.0, 0.0]

    @property
    def timeline(self) -> ScoreTimeline | None:
        return get(Get.TIMELINE, self.timeline_id)

    @property
    def timeline_ui(self) -> ScoreTimelineUI | None:
        return get(Get.TIMELINE_UI, self.timeline_id)

    def scroll_to_time(self, time: float, is_centered: bool) -> None:
        raise NotImplementedError

    def show_visible_range(
        self, start_times: list[float], end_times: list[float]
    ) -> None:
        """Puts the measure tracker over the part of the score that is shown,
        given the times its start and its end are played at. When the beat
        timeline repeats measures, it takes the times around the current one."""
        current_time = get(Get.SELECTED_TIME)
        s_idx = bisect(start_times, current_time)
        start_time = start_times[s_idx - 1 if s_idx != 0 else s_idx]
        e_idx = bisect(end_times, start_time)
        if e_idx != len(end_times):
            end_time = end_times[e_idx]
        elif start_time != 0 and end_times[0] != 0:
            end_time = get(Get.MEDIA_DURATION)
        else:
            end_time = 0
        self.update_measure_tracker(start_time, end_time)

    def update_measure_tracker(self, start: float, end: float) -> None:
        if not (timeline_ui := self.timeline_ui):
            return
        if (new_visible_times := [start, end]) == self.visible_times:
            return
        self.visible_times = new_visible_times
        if start != end:
            timeline_ui.update_measure_tracker_position(start, end)
            timeline_ui.measure_tracker.show()
        else:
            timeline_ui.measure_tracker.hide()

    def on_shown(self) -> None:
        """Brings the score up to date, after the viewer was hidden."""
        self.scroll_to_time(get(Get.SELECTED_TIME), True)

    def hideEvent(self, event: QHideEvent) -> None:
        try:
            if timeline_ui := self.timeline_ui:
                timeline_ui.measure_tracker.hide()
        except RuntimeError:
            # The timeline's scene is already deleted.
            pass
        self.is_hidden = True
        return super().hideEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        self.is_hidden = False
        if self.is_svg_loaded:
            self.on_shown()
            if timeline_ui := self.timeline_ui:
                timeline_ui.measure_tracker.show()
        return super().showEvent(event)
