"""The score viewer, drawn by Verovio. Scores stored as SVG, in older files,
keep `SvgViewer`.

Verovio's toolkit runs in a web page (`web/viewer.html`). Python drives the
page with `runJavaScript` and hears back through a web channel, whose `tilia`
object offers the page only the calls it needs. Score positions cross the
bridge as a measure number and a fraction of that measure, which the beat
timeline turns into times, as imports by measure do.
"""

from __future__ import annotations

import json
import math
from bisect import bisect
from pathlib import Path
from typing import Any, Iterable

from PySide6.QtCore import QObject, Qt, QUrl, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView

import tilia.errors
from tilia.log import logger
from tilia.requests import (
    Get,
    Post,
    get,
    listen,
    serve,
    stop_listening_to_all,
    stop_serving_all,
)
from tilia.timelines.beat.timeline import BeatTimeline
from tilia.ui import commands
from tilia.ui.windows.view_window import ViewDockWidget

VIEWER_URL = QUrl.fromLocalFile(str(Path(__file__).parent / "web" / "viewer.html"))


def _parse(payload: str) -> dict[str, Any]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        logger.error(f"Score viewer sent an unreadable message: {payload[:200]!r}")
        return {}
    return data


class _Bridge(QObject):
    """The page's `tilia` object. Its slots are all the page can call."""

    def __init__(self, score_view: ScoreView) -> None:
        super().__init__()
        self._score_view = score_view

    @Slot()
    def viewerReady(self) -> None:
        self._score_view.on_page_ready()

    @Slot(str)
    def onScoreLoaded(self, payload: str) -> None:
        self._score_view.on_score_loaded(_parse(payload))

    @Slot(str)
    def onViewportChanged(self, payload: str) -> None:
        self._score_view.on_viewport_changed(_parse(payload))

    @Slot(str)
    def onSelectionChanged(self, payload: str) -> None:
        self._score_view.on_selection_changed(_parse(payload))

    @Slot(str)
    def onElementDoubleClicked(self, payload: str) -> None:
        self._score_view.on_element_double_clicked(_parse(payload))

    @Slot(str)
    def onError(self, payload: str) -> None:
        self._score_view.on_error(_parse(payload))


class _ScorePage(QWebEnginePage):
    """Stays on the viewer: a link in a score can't take the page, and with it
    the bridge, anywhere else."""

    def acceptNavigationRequest(
        self, url: QUrl, _type: QWebEnginePage.NavigationType, _is_main_frame: bool
    ) -> bool:
        return url == VIEWER_URL

    def javaScriptConsoleMessage(
        self,
        _level: QWebEnginePage.JavaScriptConsoleMessageLevel,
        message: str,
        line: int,
        source: str,
    ) -> None:
        logger.debug(f"Score viewer: {message} ({source}:{line})")


class ScoreView(ViewDockWidget):
    """Shows a score with Verovio. It offers what `ScoreTimelineUI` calls on
    `SvgViewer`. The page loads with the first score, as Verovio takes a few
    seconds to start."""

    def __init__(self, name: str, tl_id: int, *args, **kwargs) -> None:
        super().__init__("TiLiA Score Viewer", *args, menu_title=name, **kwargs)
        self.setObjectName(f"TiLiA Score Viewer {tl_id}")
        self.setAllowedAreas(
            Qt.DockWidgetArea.BottomDockWidgetArea | Qt.DockWidgetArea.TopDockWidgetArea
        )
        self.timeline_id = tl_id
        self.view: QWebEngineView | None = None
        self._bridge: _Bridge | None = None
        self._channel: QWebChannel | None = None
        self.mei = ""
        self.is_score_loaded = False
        self.is_hidden = False
        self.visible_times = [0.0, 0.0]
        self.selected_ids: list[str] = []
        self._is_page_ready = False
        self._pending_scripts: list[str] = []
        self._element_ids: dict[int, str] = {}
        self._components_by_element: dict[str, list[int]] = {}
        self._repeated_elements: list[str] = []
        self._shown_colors: dict[str, str | None] = {}

        serve(self, Get.SCORE_VIEWER, self.get_viewer)
        listen(self, Post.PLAYER_CURRENT_TIME_CHANGED, self.on_current_time_changed)
        listen(
            self,
            Post.TIMELINE_COMPONENT_SET_DATA_DONE,
            self.on_component_set_data_done,
        )
        listen(
            self,
            Post.SCORE_TIMELINE_COMPONENTS_DESERIALIZED,
            self.on_components_deserialized,
        )

    def get_viewer(self, tl_id: int) -> ScoreView | None:
        if tl_id == self.timeline_id:
            return self

    @property
    def timeline(self):
        return get(Get.TIMELINE, self.timeline_id)

    @property
    def timeline_ui(self):
        return get(Get.TIMELINE_UI, self.timeline_id)

    @property
    def is_svg_loaded(self) -> bool:
        # The name `ScoreTimelineUI` uses for the current viewer.
        return self.is_score_loaded

    @staticmethod
    def _get_beat_timeline() -> BeatTimeline | None:
        beat_tl = get(
            Get.TIMELINE_COLLECTION
        ).get_beat_timeline_for_measure_calculation()
        return beat_tl if beat_tl and beat_tl.measure_count else None

    def get_element_id(self, component_id: int) -> str | None:
        """The id, in the score, of the element a note component stands for."""
        return self._element_ids.get(component_id)

    def load_score(self, text: str, element_ids: dict[int, str] | None = None) -> None:
        """Shows a score given as MusicXML or MEI. `element_ids` maps the
        timeline's note components to the ids of their elements in the score."""
        self.is_score_loaded = False
        self.mei = ""
        self.selected_ids = []
        self._element_ids = dict(element_ids or {})
        self._components_by_element = {}
        for component_id, element_id in self._element_ids.items():
            self._components_by_element.setdefault(element_id, []).append(component_id)
        self._repeated_elements = [
            element_id
            for element_id, component_ids in self._components_by_element.items()
            if len(component_ids) > 1
        ]
        self._shown_colors = {}

        self._setup_page()
        self._run_script("tiliaLoadScore", text)

        self.setParent(get(Get.MAIN_WINDOW))
        if not self.isVisible() and not self.is_hidden:
            self.parentWidget().addDockWidget(
                Qt.DockWidgetArea.BottomDockWidgetArea, self
            )
            self.show()

    def _setup_page(self) -> None:
        if self.view:
            return
        self.view = QWebEngineView(self)
        page = _ScorePage(self.view)
        page.setBackgroundColor(Qt.GlobalColor.white)
        self.view.setPage(page)
        self._bridge = _Bridge(self)
        self._channel = QWebChannel(page)
        self._channel.registerObject("tilia", self._bridge)
        page.setWebChannel(self._channel)
        self.setWidget(self.view)
        self.view.load(VIEWER_URL)

    def _run_script(self, function: str, *args: Any) -> None:
        script = f"{function}({', '.join(json.dumps(arg) for arg in args)})"
        if self._is_page_ready:
            self.view.page().runJavaScript(script)
        else:
            self._pending_scripts.append(script)

    def on_page_ready(self) -> None:
        self._is_page_ready = True
        for script in self._pending_scripts:
            self.view.page().runJavaScript(script)
        self._pending_scripts = []

    def on_score_loaded(self, data: dict[str, Any]) -> None:
        self.mei = data.get("mei", "")
        self.is_score_loaded = True
        self._update_colors(self._components_by_element)
        self.scroll_to_time(get(Get.SELECTED_TIME), True)

    def on_error(self, data: dict[str, Any]) -> None:
        tilia.errors.display(
            tilia.errors.SCORE_SVG_CREATE_ERROR, data.get("message", "")
        )

    def _get_times(self, position: Any) -> list[float] | None:
        """The times the beat timeline places a score position at, or None
        if they can't be known."""
        beat_tl = self._get_beat_timeline()
        if not beat_tl or not isinstance(position, dict):
            return None
        try:
            number = int(position["measure"])
            fraction = min(max(float(position["fraction"]), 0.0), 1.0)
        except (KeyError, TypeError, ValueError):
            return None
        if times := beat_tl.get_time_by_measure(number, fraction):
            return times
        return (
            [0] if number < min(beat_tl.measure_numbers) else [get(Get.MEDIA_DURATION)]
        )

    def on_viewport_changed(self, data: dict[str, Any]) -> None:
        start_times = self._get_times(data.get("start"))
        end_times = self._get_times(data.get("end"))
        if not start_times or not end_times:
            return

        # Of all the times the visible measures are played at, show the ones
        # around the current time, as SvgViewer does.
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
        if (new_visible_times := [start, end]) == self.visible_times:
            return
        self.visible_times = new_visible_times
        if start != end:
            self.timeline_ui.update_measure_tracker_position(start, end)
            self.timeline_ui.measure_tracker.show()
        else:
            self.timeline_ui.measure_tracker.hide()

    def on_selection_changed(self, data: dict[str, Any]) -> None:
        ids = data.get("ids", [])
        self.selected_ids = [id for id in ids if isinstance(id, str)]

    def on_element_double_clicked(self, data: dict[str, Any]) -> None:
        if not (times := self._get_times(data)):
            return
        current_time = get(Get.SELECTED_TIME)
        commands.execute("media.seek", min(times, key=lambda t: abs(t - current_time)))

    def scroll_to_time(self, time: float, is_centered: bool) -> None:
        if not self.is_score_loaded or not (beat_tl := self._get_beat_timeline()):
            return
        metric_fraction = beat_tl.get_metric_fraction_by_time(time)
        number = math.floor(metric_fraction)
        self._run_script("tiliaScrollTo", number, metric_fraction - number, is_centered)

    def _get_color(self, component_ids: list[int], time: float) -> str | None:
        # A note played more than once shows the colour of the time it's
        # played nearest the current time; on a tie, the earlier one.
        timeline = self.timeline
        nearest = None
        for component_id in component_ids:
            try:
                start = timeline.get_component_data(component_id, "start")
                end = timeline.get_component_data(component_id, "end")
            except KeyError:
                continue
            key = (max(start - time, time - end, 0), start)
            if nearest is None or key < nearest[0]:
                nearest = (key, component_id)
        if nearest is None:
            return None
        return timeline.get_component_data(nearest[1], "color")

    def _update_colors(self, element_ids: Iterable[str]) -> None:
        if not self.is_score_loaded or not self.timeline:
            return
        time = get(Get.SELECTED_TIME)
        changed = {}
        for element_id in element_ids:
            color = self._get_color(self._components_by_element[element_id], time)
            if self._shown_colors.get(element_id) != color:
                changed[element_id] = color
        if changed:
            self._shown_colors.update(changed)
            self._run_script("tiliaSetColors", changed)

    def on_current_time_changed(self, _time: float, _reason: Any) -> None:
        self._update_colors(self._repeated_elements)

    def on_component_set_data_done(
        self, timeline_id: int, component_id: int, attr: str, _value: Any
    ) -> None:
        if timeline_id != self.timeline_id or attr != "color":
            return
        if element_id := self._element_ids.get(component_id):
            self._update_colors([element_id])

    def on_components_deserialized(self, timeline_id: int) -> None:
        if timeline_id == self.timeline_id:
            self._update_colors(self._components_by_element)

    def update_annotation(self, tl_component_id: int) -> None:
        """Score annotations aren't shown by this viewer yet."""

    def remove_annotation(self, tl_component_id: int) -> None:
        """Score annotations aren't shown by this viewer yet."""

    def deleteLater(self) -> None:
        stop_serving_all(self)
        stop_listening_to_all(self)
        super().deleteLater()

    def hideEvent(self, event) -> None:
        try:
            if timeline_ui := self.timeline_ui:
                timeline_ui.measure_tracker.hide()
        except RuntimeError:
            pass
        self.is_hidden = True
        return super().hideEvent(event)

    def showEvent(self, event) -> None:
        self.scroll_to_time(get(Get.SELECTED_TIME), True)
        if self.timeline_ui and self.is_score_loaded:
            self.timeline_ui.measure_tracker.show()
        self.is_hidden = False
        return super().showEvent(event)
