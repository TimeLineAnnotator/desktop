"""The score viewer, drawn by Verovio. Scores stored as SVG, in older files,
keep `SvgViewer`.

Verovio's toolkit runs in a web page (`web/viewer.html`). Python drives the
page with `runJavaScript` and hears back through a web channel, whose `tilia`
object offers the page only the calls it needs. Score positions cross the
bridge as a measure number and a fraction of that measure, which the beat
timeline turns into times, as imports by measure do.
"""

from __future__ import annotations

import bisect
import json
import math
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from PySide6.QtCore import QObject, QSize, Qt, QTimer, QUrl, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

import tilia.errors
from tilia.log import logger
from tilia.requests import (
    Get,
    Post,
    get,
    listen,
    post,
    stop_listening_to_all,
)
from tilia.settings import settings
from tilia.timelines.component_kinds import ComponentKind
from tilia.ui import commands
from tilia.ui.enums import WindowState
from tilia.ui.windows.score.base import (
    ScoreViewerBase,
    get_beat_timeline,
    get_times_at,
)
from tilia.ui.windows.score.group_panel import GroupPanel, format_prime_form
from tilia.ui.windows.score.group_table import GroupRow, GroupTableWindow

if TYPE_CHECKING:
    from tilia.timelines.beat.timeline import BeatTimeline
    from tilia.timelines.score.components import NoteGroup
    from tilia.timelines.score.pcset import PitchClassSetAnalysis
    from tilia.timelines.score.timeline import ScoreTimeline

VIEWER_PATH = Path(__file__).parent / "web" / "viewer.html"
VIEWER_URL = QUrl.fromLocalFile(str(VIEWER_PATH))

# The visible range is looked up at this resolution: the beat timeline keeps
# every position it's asked about, and scrolling would ask about thousands.
VIEWPORT_STEPS_PER_MEASURE = 32

# How often the page is restarted after its process dies, before giving up.
MAX_PAGE_RESTARTS = 2


def _metric_position(
    beat_tl: BeatTimeline, time: float, beat_times: list[float]
) -> float:
    """Where `time` falls as a measure number plus a fraction of the measure.
    Past the last of the `beat_times`, the last measure goes on at the pace of
    its last beat, up to its end."""
    position = beat_tl.get_metric_fraction_by_time(time)
    if len(beat_times) < 2 or time <= beat_times[-1]:
        return position
    beat_length = beat_times[-1] - beat_times[-2]
    past = (time - beat_times[-1]) / beat_length / beat_tl.beats_in_measure[-1]
    return min(position + past, math.floor(position) + 1)


def _span_positions(
    beat_tl: BeatTimeline, start: float, end: float, beat_times: list[float]
) -> list[tuple[float, float]]:
    """The metric positions from `start` to `end`, split where the measures
    don't follow each other, as where a repeat goes back."""
    segments = []
    segment_start = previous = _metric_position(beat_tl, start, beat_times)
    inner_beats = beat_times[
        bisect.bisect_right(beat_times, start) : bisect.bisect_left(beat_times, end)
    ]
    for time in [*inner_beats, end]:
        position = _metric_position(beat_tl, time, beat_times)
        # Back, even within the measure (a measure played twice in a row), or
        # past the next measure.
        if position < previous or math.floor(position) > math.floor(previous) + 1:
            # The segment so far ends with the measure it is in.
            segments.append((segment_start, math.floor(previous) + 1))
            segment_start = position
        previous = position
    segments.append((segment_start, previous))
    return [(a, b) for a, b in segments if b > a]


def _measure_ranges(
    beat_tl: BeatTimeline, spans: Iterable[tuple[float, float | None]]
) -> list[list[float]]:
    """The score ranges that `spans` cover, as a start measure and fraction
    and an end measure and fraction. A time with no end covers its measure.
    Overlapping ranges are joined."""
    beat_times = sorted(beat.time for beat in beat_tl)
    positions = []
    for start, end in spans:
        if end is None:
            measure = math.floor(_metric_position(beat_tl, start, beat_times))
            positions.append((measure, measure + 1))
        else:
            positions += _span_positions(beat_tl, start, end, beat_times)
    joined: list[list[float]] = []
    for start, end in sorted(positions):
        if joined and start <= joined[-1][1]:
            joined[-1][1] = max(joined[-1][1], end)
        else:
            joined.append([start, end])
    ranges = []
    for start, end in joined:
        start_measure = math.floor(start)
        # An end on a barline ends the measure before it, which may be the last.
        end_measure = math.ceil(end) - 1
        ranges.append(
            [start_measure, start - start_measure, end_measure, end - end_measure]
        )
    return ranges


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


SCORE_MIN_HEIGHT = 200
SCORE_INITIAL_HEIGHT = 450


class _ScoreContainer(QWidget):
    """The viewer's contents. The main window sizes a new dock by this hint."""

    def sizeHint(self) -> QSize:
        return QSize(super().sizeHint().width(), SCORE_INITIAL_HEIGHT)


class ScoreView(ScoreViewerBase):
    """Shows a score with Verovio. It offers what `ScoreTimelineUI` calls on
    `SvgViewer`. The page loads with the first score, as Verovio takes a few
    seconds to start."""

    def __init__(self, name: str, tl_id: int, *args, **kwargs) -> None:
        super().__init__(name, tl_id, *args, **kwargs)
        self.view: QWebEngineView | None = None
        self._bridge: _Bridge | None = None
        self._channel: QWebChannel | None = None
        self.mei = ""
        self.is_score_loaded = False
        self.selected_ids: list[str] = []
        # The selected elements' notes: a chord's, for one.
        self.selected_note_ids: list[str] = []
        self.active_group_id: str | None = None
        self.group_panel: GroupPanel | None = None
        self.group_table_window: GroupTableWindow | None = None
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
        # Whether the page shades what's selected in other timelines, and
        # whether an update of that shading is on its way.
        self._has_highlights = False
        self._is_highlight_update_pending = False
        self._should_reveal_highlights = False
        # In pages, the score is broken into systems as wide as the viewer and
        # scrolls down; otherwise it is one system, scrolled sideways.
        self.is_page_view = bool(settings.get("score_timeline", "page_view"))

        listen(self, Post.PLAYER_CURRENT_TIME_CHANGED, self.on_current_time_changed)
        listen(self, Post.TIMELINE_COMPONENT_SELECTED, self.on_selection_changed_in)
        listen(self, Post.TIMELINE_COMPONENT_DESELECTED, self.on_selection_changed_in)
        listen(self, Post.TIMELINE_DELETE_DONE, self.on_timelines_changed)
        listen(self, Post.APP_STATE_RESTORE, self.on_timelines_changed)
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

    @property
    def is_svg_loaded(self) -> bool:
        return self.is_score_loaded

    def get_element_id(self, component_id: int) -> str | None:
        """The id, in the score, of the element a note component stands for."""
        return self._element_ids.get(component_id)

    def load_score(self, text: str, element_ids: dict[int, str] | None = None) -> None:
        """Shows a score given as MusicXML or MEI. `element_ids` maps the
        timeline's note components to the ids of their elements in the score."""
        self._forget_score()
        self._set_element_ids(element_ids or {})

        self._setup_page()
        self._score_text = text
        self._run_script("tiliaLoadScore", text, self._layout)

        main_window = get(Get.MAIN_WINDOW)
        if self.parentWidget() is not main_window:
            # The first score puts the viewer below the timelines. Later ones,
            # after a clear, find it where it was.
            self.setParent(main_window)
            main_window.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self)
        if not self.is_hidden:
            self.show()

    def clear_score(self) -> None:
        """Forgets the score, as its timeline was cleared, and closes the
        viewer as deleting it would. The page stays, so that the next score
        doesn't start Verovio again, and so does the viewer's place."""
        self._forget_score()
        self._set_element_ids({})
        self._score_text = None
        # A score the page hasn't shown yet.
        self._pending_scripts = []
        if self.is_registered:
            post(Post.WINDOW_UPDATE_STATE, self.id, WindowState.DELETED)
            self.is_registered = False
        self.hide()
        if self.group_table_window:
            self.group_table_window.close()
        # Not closed by the user: the next score shows the viewer again.
        self.is_hidden = False

    def _forget_score(self) -> None:
        self.is_score_loaded = False
        self.mei = ""
        self.selected_ids = []
        self.selected_note_ids = []
        self.active_group_id = None
        self._varying_elements = set()
        self._shown_colors = {}
        self._has_highlights = False

    def _set_element_ids(self, element_ids: dict[int, str]) -> None:
        self._element_ids = dict(element_ids)
        self._components_by_element = {}
        for component_id, element_id in self._element_ids.items():
            self._components_by_element.setdefault(element_id, []).append(component_id)
        self._repeated_elements = [
            element_id
            for element_id, component_ids in self._components_by_element.items()
            if len(component_ids) > 1
        ]

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
        self.group_panel = GroupPanel(self.timeline_id)
        self.group_panel.pages_button.setChecked(self.is_page_view)
        container = _ScoreContainer(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.group_panel)
        # The score keeps room in a small window: the panel doesn't push it out.
        self.view.setMinimumHeight(SCORE_MIN_HEIGHT)
        layout.addWidget(self.view, stretch=1)
        self.group_table_window = GroupTableWindow(
            self.timeline_id, self.menu_title, self.group_panel.table_button.setChecked
        )
        self.setWidget(container)
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
                self._script("tiliaLoadScore", self._score_text, self._layout)
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
        if self._score_text is None:
            # The score was cleared while the page was showing it.
            return
        self.mei = data.get("mei", "")
        self.is_score_loaded = True
        self._page_restarts = 0
        self._update_varying(self._repeated_elements)
        self._update_colors(self._components_by_element)
        self.show_note_groups()
        self.scroll_to_time(get(Get.SELECTED_TIME), True)
        self._update_highlights()

    def on_error(self, data: dict[str, Any]) -> None:
        tilia.errors.display(
            tilia.errors.SCORE_SVG_CREATE_ERROR, data.get("message", "")
        )

    def _get_times(self, position: Any, snap: bool = False) -> list[float] | None:
        """The times the beat timeline places a score position at, or None
        if they can't be known. `snap` rounds the position to one of
        `VIEWPORT_STEPS_PER_MEASURE` steps of its measure."""
        beat_tl = get_beat_timeline()
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
        return get_times_at(beat_tl, number, fraction)

    def on_viewport_changed(self, data: dict[str, Any]) -> None:
        if self.is_hidden or not self.is_score_loaded:
            return
        start_times = self._get_times(data.get("start"), snap=True)
        end_times = self._get_times(data.get("end"), snap=True)
        if start_times and end_times:
            self.show_visible_range(start_times, end_times)

    def on_selection_changed(self, data: dict[str, Any]) -> None:
        ids = data.get("ids", [])
        self.selected_ids = [id for id in ids if isinstance(id, str)]
        note_ids = data.get("noteIds", [])
        self.selected_note_ids = [id for id in note_ids if isinstance(id, str)]
        group = data.get("group")
        self.active_group_id = group if isinstance(group, str) else None
        self._update_group_panel()
        if self.group_table_window:
            self.group_table_window.table.select_group(self.active_group_id)

    def _note_groups(self) -> list[NoteGroup]:
        if not (timeline := self.timeline):
            return []
        return [
            c
            for c in timeline.component_manager.get_components()
            if c.KIND == ComponentKind.NOTE_GROUP
        ]

    def show_note_groups(self, active_group: str | None = None) -> None:
        """Draws the timeline's note groups on the score. An `active_group`
        becomes the group shown in the panel, with its notes selected."""
        if not self.is_score_loaded:
            return
        groups = []
        rows = []
        for group in self._note_groups():
            analysis = group.analysis
            prime = format_prime_form(analysis)
            groups.append(
                {
                    "id": group.id,
                    "ids": group.element_ids,
                    "color": group.color,
                    "text": f"{group.label}: {prime}" if group.label else prime,
                }
            )
            rows.append(self._group_row(group, analysis))
        self._run_script("tiliaSetGroups", groups, active_group)
        if self.group_table_window:
            self.group_table_window.show_groups(
                rows, active_group or self.active_group_id
            )

    def _group_row(self, group: NoteGroup, analysis: PitchClassSetAnalysis) -> GroupRow:
        starts = self.timeline.get_element_start_times(group.element_ids)
        start, end = (min(starts), max(starts)) if starts else (math.inf, math.inf)
        return GroupRow(
            group.id,
            group.label,
            group.color,
            analysis,
            self._measures_text(start, end) if starts else "",
            start,
            end,
        )

    @staticmethod
    def _measures_text(start: float, end: float) -> str:
        if not (beat_tl := get_beat_timeline()):
            return ""
        first = math.floor(beat_tl.get_metric_fraction_by_time(start))
        last = math.floor(beat_tl.get_metric_fraction_by_time(end))
        return str(first) if first == last else f"{first}\u2013{last}"

    @property
    def _layout(self) -> str:
        return "pages" if self.is_page_view else "continuous"

    def set_page_view(self, is_page_view: bool) -> None:
        """Shows the score in pages scrolled down, or in one system scrolled
        sideways."""
        self.is_page_view = is_page_view
        if self.group_panel:
            self.group_panel.pages_button.setChecked(is_page_view)
        if self._score_text is not None:
            self._run_script("tiliaSetLayout", self._layout)

    def toggle_page_view(self) -> None:
        self.set_page_view(not self.is_page_view)

    def select_note_group(self, group_id: str) -> None:
        """Makes a group the active one and brings it into view."""
        self._run_script("tiliaShowGroup", group_id)

    def toggle_group_table(self) -> None:
        if not (window := self.group_table_window):
            return
        if window.isHidden():
            window.show()
            window.raise_()
        else:
            window.close()

    def export_group_table(self, path: str | None = None) -> None:
        if not (window := self.group_table_window) or not window.table.rowCount():
            return
        if path is None:
            accepted, path = get(
                Get.FROM_USER_SAVE_PATH,
                title="Export note groups",
                filter="CSV files (*.csv)",
                initial_filename=f"{self.menu_title} note groups.csv",
            )
            if not accepted:
                return
        path = Path(path)
        if not path.suffix:
            path = path.with_suffix(".csv")
        try:
            window.table.write_csv(path)
        except OSError as error:
            tilia.errors.display(tilia.errors.EXPORT_NOTE_GROUPS_FAILED, path, error)

    def _update_group_panel(self) -> None:
        if not self.group_panel or not (timeline := self.timeline):
            return
        analysis = (
            timeline.analyse_elements(self.selected_note_ids)
            if self.selected_note_ids
            else None
        )
        group = next(
            (g for g in self._note_groups() if g.id == self.active_group_id), None
        )
        self.group_panel.show_state(
            analysis, group.id if group else None, group.label if group else ""
        )

    def on_element_double_clicked(self, data: dict[str, Any]) -> None:
        if not (times := self._get_times(data)):
            return
        current_time = get(Get.SELECTED_TIME)
        commands.execute("media.seek", min(times, key=lambda t: abs(t - current_time)))

    def scroll_to_time(self, time: float, is_centered: bool) -> None:
        if not self.is_score_loaded or not (beat_tl := get_beat_timeline()):
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
        if timeline_id != self.timeline_id:
            # A selected component may have moved, or the beats under it.
            self._schedule_highlight_update()
            return
        if attr != "color":
            return
        if element_id := self._element_ids.get(component_id):
            self._update_varying([element_id])
            self._update_colors([element_id])

    def on_selection_changed_in(self, timeline_id: int, _element_id: int) -> None:
        if timeline_id != self.timeline_id:
            # Only a new selection scrolls to it: an edit or the user's
            # scrolling shouldn't be undone.
            self._should_reveal_highlights = True
            self._schedule_highlight_update()

    def on_timelines_changed(self, *_: Any) -> None:
        # Selected elements may have gone with their timeline, without being
        # deselected.
        self._schedule_highlight_update()

    def _schedule_highlight_update(self) -> None:
        # Once for all the elements a selection box or a select-all changes.
        if not self._is_highlight_update_pending:
            self._is_highlight_update_pending = True
            QTimer.singleShot(0, self, self._update_highlights)

    def _update_highlights(self) -> None:
        """Shades, behind the score, what's selected in other timelines."""
        self._is_highlight_update_pending = False
        beat_tl = get_beat_timeline()
        if not self.is_score_loaded or not beat_tl:
            return
        ranges = _measure_ranges(beat_tl, self._selected_spans())
        if ranges or self._has_highlights:
            self._run_script(
                "tiliaSetHighlights", ranges, self._should_reveal_highlights
            )
        self._has_highlights = bool(ranges)
        self._should_reveal_highlights = False

    def _selected_spans(self) -> list[tuple[float, float | None]]:
        """The times of the components selected in other timelines: a start
        and an end, or a time and None."""
        spans = []
        for timeline_ui in get(Get.TIMELINE_UIS):
            if timeline_ui.id == self.timeline_id:
                continue
            # A slider timeline has no components.
            if not (manager := timeline_ui.timeline.component_manager):
                continue
            components = manager.id_to_component
            for element in timeline_ui.selected_elements:
                if not (component := components.get(element.id)):
                    continue
                start = getattr(component, "start", None)
                end = getattr(component, "end", None)
                if start is not None and end is not None:
                    spans.append((start, end))
                elif (time := getattr(component, "time", None)) is not None:
                    spans.append((time, None))
        return spans

    def on_components_deserialized(self, timeline_id: int) -> None:
        if timeline_id == self.timeline_id:
            self._update_varying(self._repeated_elements)
            self._update_colors(self._components_by_element)
            self.show_note_groups()

    def update_annotation(self, tl_component_id: int) -> None:
        """Score annotations aren't shown by this viewer yet."""

    def remove_annotation(self, tl_component_id: int) -> None:
        """Score annotations aren't shown by this viewer yet."""

    def deleteLater(self) -> None:
        if self._bridge:
            self._bridge.detach()
        if self.group_table_window:
            self.group_table_window.hide()
            self.group_table_window.deleteLater()
        stop_listening_to_all(self)
        super().deleteLater()

    def on_shown(self) -> None:
        super().on_shown()
        # The range may have changed while the viewer was hidden.
        self._run_script("tiliaReportViewport")
