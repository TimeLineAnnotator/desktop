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
import os
from bisect import bisect
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from PySide6.QtCore import QObject, Qt, QUrl, Slot
from PySide6.QtGui import QHideEvent, QShowEvent
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

if TYPE_CHECKING:
    from tilia.timelines.score.timeline import ScoreTimeline
    from tilia.ui.timelines.score.timeline import ScoreTimelineUI

VIEWER_PATH = Path(__file__).parent / "web" / "viewer.html"
VIEWER_URL = QUrl.fromLocalFile(str(VIEWER_PATH))

# The visible range is looked up at this resolution: the beat timeline keeps
# every position it's asked about, and scrolling would ask about thousands.
VIEWPORT_STEPS_PER_MEASURE = 32

# How often the page is restarted after its process dies, before giving up.
MAX_PAGE_RESTARTS = 2


def _parse(payload: str) -> dict[str, Any]:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        logger.error(f"Score viewer sent an unreadable message: {payload[:200]!r}")
        return {}
    return data


def _is_viewer(url: QUrl) -> bool:
    if not url.isLocalFile():
        return False
    # Paths, not URLs: Chromium writes a Windows drive letter in upper case.
    return os.path.normcase(os.path.abspath(url.toLocalFile())) == os.path.normcase(
        os.path.abspath(VIEWER_PATH)
    )


class _Bridge(QObject):
    """The page's `tilia` object. Its slots are all the page can call."""

    def __init__(self, score_view: ScoreView) -> None:
        super().__init__()
        self._score_view: ScoreView | None = score_view

    def detach(self) -> None:
        # Messages the page sent before its viewer was deleted are dropped.
        self._score_view = None

    @Slot()
    def viewerReady(self) -> None:
        if self._score_view:
            self._score_view.on_page_ready()

    @Slot(str)
    def onScoreLoaded(self, payload: str) -> None:
        if self._score_view:
            self._score_view.on_score_loaded(_parse(payload))

    @Slot(str)
    def onViewportChanged(self, payload: str) -> None:
        if self._score_view:
            self._score_view.on_viewport_changed(_parse(payload))

    @Slot(str)
    def onSelectionChanged(self, payload: str) -> None:
        if self._score_view:
            self._score_view.on_selection_changed(_parse(payload))

    @Slot(str)
    def onElementDoubleClicked(self, payload: str) -> None:
        if self._score_view:
            self._score_view.on_element_double_clicked(_parse(payload))

    @Slot(str)
    def onError(self, payload: str) -> None:
        if self._score_view:
            self._score_view.on_error(_parse(payload))


class _ScorePage(QWebEnginePage):
    """Stays on the viewer: a link in a score can't take the page, and with it
    the bridge, anywhere else."""

    def acceptNavigationRequest(
        self, url: QUrl, _type: QWebEnginePage.NavigationType, _is_main_frame: bool
    ) -> bool:
        return _is_viewer(url)

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
        self._score_text: str | None = None
        self._is_page_ready = False
        self._page_restarts = 0
        self._pending_scripts: list[str] = []
        self._element_ids: dict[int, str] = {}
        self._components_by_element: dict[str, list[int]] = {}
        self._repeated_elements: list[str] = []
        # Repeated elements whose occurrences differ in colour, so that the
        # colour shown depends on the current time.
        self._varying_elements: set[str] = set()
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
    def timeline(self) -> ScoreTimeline | None:
        return get(Get.TIMELINE, self.timeline_id)

    @property
    def timeline_ui(self) -> ScoreTimelineUI | None:
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
        self._varying_elements = set()
        self._shown_colors = {}

        self._setup_page()
        self._score_text = text
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
        # Its Reload, Back and View Source would take the page off the score.
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        page = _ScorePage(self.view)
        page.setBackgroundColor(Qt.GlobalColor.white)
        page.loadStarted.connect(self._on_load_started)
        page.renderProcessTerminated.connect(self._on_render_process_terminated)
        self.view.setPage(page)
        self._bridge = _Bridge(self)
        self._channel = QWebChannel(page)
        self._channel.registerObject("tilia", self._bridge)
        page.setWebChannel(self._channel)
        self.setWidget(self.view)
        self.view.load(VIEWER_URL)

    @staticmethod
    def _script(function: str, *args: Any) -> str:
        return f"{function}({', '.join(json.dumps(arg) for arg in args)})"

    def _run_script(self, function: str, *args: Any) -> None:
        script = self._script(function, *args)
        if self._is_page_ready:
            self.view.page().runJavaScript(script)
        else:
            self._pending_scripts.append(script)

    def _on_load_started(self) -> None:
        # The page reloaded, or restarted after its process died, and lost its
        # score: show it again once the page is ready.
        self._is_page_ready = False
        if self._score_text is not None and not self._pending_scripts:
            self.is_score_loaded = False
            self._shown_colors = {}
            self._pending_scripts.append(
                self._script("tiliaLoadScore", self._score_text)
            )

    def _on_render_process_terminated(
        self, status: QWebEnginePage.RenderProcessTerminationStatus, code: int
    ) -> None:
        if (
            status
            == QWebEnginePage.RenderProcessTerminationStatus.NormalTerminationStatus
        ):
            return
        logger.error(f"Score viewer's page stopped ({status}, exit code {code}).")
        if self._page_restarts < MAX_PAGE_RESTARTS:
            self._page_restarts += 1
            self.view.reload()

    def on_page_ready(self) -> None:
        self._is_page_ready = True
        for script in self._pending_scripts:
            self.view.page().runJavaScript(script)
        self._pending_scripts = []

    def on_score_loaded(self, data: dict[str, Any]) -> None:
        self.mei = data.get("mei", "")
        self.is_score_loaded = True
        self._page_restarts = 0
        self._update_varying(self._repeated_elements)
        self._update_colors(self._components_by_element)
        self.scroll_to_time(get(Get.SELECTED_TIME), True)

    def on_error(self, data: dict[str, Any]) -> None:
        tilia.errors.display(
            tilia.errors.SCORE_SVG_CREATE_ERROR, data.get("message", "")
        )

    def _get_times(self, position: Any, snap: bool = False) -> list[float] | None:
        """The times the beat timeline places a score position at, or None
        if they can't be known. `snap` rounds the position to one of
        `VIEWPORT_STEPS_PER_MEASURE` steps of its measure."""
        beat_tl = self._get_beat_timeline()
        if not beat_tl or not isinstance(position, dict):
            return None
        try:
            number = int(position["measure"])
            fraction = min(max(float(position["fraction"]), 0.0), 1.0)
        except (KeyError, TypeError, ValueError):
            return None
        if snap:
            steps = VIEWPORT_STEPS_PER_MEASURE
            fraction = round(fraction * steps) / steps
        if times := beat_tl.get_time_by_measure(number, fraction):
            return times
        return (
            [0] if number < min(beat_tl.measure_numbers) else [get(Get.MEDIA_DURATION)]
        )

    def on_viewport_changed(self, data: dict[str, Any]) -> None:
        if self.is_hidden:
            return
        start_times = self._get_times(data.get("start"), snap=True)
        end_times = self._get_times(data.get("end"), snap=True)
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

    @staticmethod
    def _get_color(
        timeline: ScoreTimeline, component_ids: list[int], time: float
    ) -> str | None:
        # A note played more than once shows the colour of the time it's
        # played nearest the current time; on a tie, the earlier one.
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

    def _update_varying(self, element_ids: Iterable[str]) -> None:
        if not (timeline := self.timeline):
            return
        for element_id in element_ids:
            colors = set()
            for component_id in self._components_by_element.get(element_id, []):
                try:
                    colors.add(timeline.get_component_data(component_id, "color"))
                except KeyError:
                    continue
            if len(colors) > 1:
                self._varying_elements.add(element_id)
            else:
                self._varying_elements.discard(element_id)

    def _update_colors(
        self, element_ids: Iterable[str], time: float | None = None
    ) -> None:
        if not self.is_score_loaded or not (timeline := self.timeline):
            return
        if time is None:
            time = get(Get.SELECTED_TIME)
        changed = {}
        for element_id in element_ids:
            color = self._get_color(
                timeline, self._components_by_element[element_id], time
            )
            if self._shown_colors.get(element_id) != color:
                changed[element_id] = color
        if changed:
            self._shown_colors.update(changed)
            self._run_script("tiliaSetColors", changed)

    def on_current_time_changed(self, time: float, _reason: Any) -> None:
        # The time posted, not Get.SELECTED_TIME, which smooth scrolling
        # updates only later.
        if self._varying_elements:
            self._update_colors(list(self._varying_elements), time)

    def on_component_set_data_done(
        self, timeline_id: int, component_id: int, attr: str, _value: Any
    ) -> None:
        if timeline_id != self.timeline_id or attr != "color":
            return
        if element_id := self._element_ids.get(component_id):
            self._update_varying([element_id])
            self._update_colors([element_id])

    def on_components_deserialized(self, timeline_id: int) -> None:
        if timeline_id == self.timeline_id:
            self._update_varying(self._repeated_elements)
            self._update_colors(self._components_by_element)

    def update_annotation(self, tl_component_id: int) -> None:
        """Score annotations aren't shown by this viewer yet."""

    def remove_annotation(self, tl_component_id: int) -> None:
        """Score annotations aren't shown by this viewer yet."""

    def deleteLater(self) -> None:
        if self._bridge:
            self._bridge.detach()
        stop_serving_all(self)
        stop_listening_to_all(self)
        super().deleteLater()

    def hideEvent(self, event: QHideEvent) -> None:
        try:
            if timeline_ui := self.timeline_ui:
                timeline_ui.measure_tracker.hide()
        except RuntimeError:
            pass
        self.is_hidden = True
        return super().hideEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        self.is_hidden = False
        if self.is_score_loaded:
            self.scroll_to_time(get(Get.SELECTED_TIME), True)
            # The range may have changed while the viewer was hidden.
            self._run_script("tiliaReportViewport")
            if timeline_ui := self.timeline_ui:
                timeline_ui.measure_tracker.show()
        return super().showEvent(event)
