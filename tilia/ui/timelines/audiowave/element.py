from __future__ import annotations

import math

import numpy as np
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem

from tilia.requests import Post, listen, stop_listening
from tilia.settings import settings
from tilia.ui.timelines.base.element import TimelineUIElement

from ...coords import time_x_converter
from ..cursors import CursorMixIn


class WaveformElement(TimelineUIElement):
    UPDATE_TRIGGERS = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.body = WaveformItem(self)
        self.scene.addItem(self.body)
        listen(self, Post.AUDIOWAVE_PEAKS_READY, self._on_peaks_ready)

    @property
    def waveform_component(self):
        return self.tl_component

    @property
    def height(self) -> int:
        return self.timeline_ui.get_data("height")

    def child_items(self):
        return [self.body]

    def left_click_triggers(self):
        return [self.body]

    def update_position(self):
        # Scene width / zoom changed — invalidate bounding rect and repaint.
        self.body.prepareGeometryChange()
        self.body.update()

    def _on_peaks_ready(self, timeline_id: int, component_id: int) -> None:
        if timeline_id != self.timeline_ui.id:
            return
        if component_id != self.id:
            return
        self.body.stop_spinner()
        self.body.update()

    def on_select(self) -> None:
        # Waveform isn't selectable — keep the no-op for the abstract contract.
        pass

    def on_deselect(self) -> None:
        pass

    def delete(self):
        stop_listening(self, Post.AUDIOWAVE_PEAKS_READY)
        self.body.cleanup()
        super().delete()


class WaveformItem(CursorMixIn, QGraphicsItem):
    LOADING_SPINNER_INTERVAL_MS = 40
    LOADING_SPINNER_DEG_PER_FRAME = 10
    LOADING_SPINNER_ARC_DEG = 90
    LOADING_SPINNER_MIN_DIAMETER = 18.0
    LOADING_SPINNER_MAX_DIAMETER = 36.0

    def __init__(self, element: WaveformElement):
        super().__init__(cursor_shape=Qt.CursorShape.PointingHandCursor)
        self.element = element
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self._spinner_angle = 0.0
        self._spinner_timer = QTimer()
        self._spinner_timer.setInterval(self.LOADING_SPINNER_INTERVAL_MS)
        self._spinner_timer.timeout.connect(self._tick_spinner)

    def _tick_spinner(self) -> None:
        self._spinner_angle = (
            self._spinner_angle + self.LOADING_SPINNER_DEG_PER_FRAME
        ) % 360.0
        self.update()

    def start_spinner(self) -> None:
        if not self._spinner_timer.isActive():
            self._spinner_timer.start()

    def stop_spinner(self) -> None:
        if self._spinner_timer.isActive():
            self._spinner_timer.stop()

    def cleanup(self) -> None:
        self.stop_spinner()
        self._spinner_timer.deleteLater()

    def boundingRect(self) -> QRectF:
        # Cover the full scene width so the item's exposed-rect is always
        # well-defined (including the margin areas Qt may invalidate).
        scene = self.scene()
        width = scene.width() if scene is not None else 0
        return QRectF(0, 0, float(width), float(self.element.height))

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def _data_x_bounds(self, wf) -> tuple[float, float] | None:
        """Scene-x range over which the audio waveform is drawn.

        Anchored to the time axis (so x=time_x_converter.get_x_by_time(t)
        for every t between 0 and the audio duration).  Returns ``None``
        when there is no usable data.
        """
        if wf.samplerate <= 0 or wf.total_frames <= 0:
            return None
        duration = wf.total_frames / wf.samplerate
        x_start = time_x_converter.get_x_by_time(0.0)
        x_end = time_x_converter.get_x_by_time(duration)
        if x_end <= x_start:
            return None
        return float(x_start), float(x_end)

    def _visible_x_range(self, bounding: QRectF) -> tuple[float, float]:
        """Visible inner-scene-x range, derived from the outer view.

        The inner ``TimelineView`` always paints the full inner scene
        (it has a fixed width matching ``Get.TIMELINE_WIDTH``); the user
        only ever sees a slice because the outer ``TimelineUIsView``
        scrolls.  Mapping the outer viewport back into our coordinates
        gives us the slice we actually need to draw.
        """
        try:
            outer_view = self.element.timeline_ui.collection.view
            viewport = outer_view.current_viewport_x
            proxy = self.element.timeline_ui.view.proxy
            offset = proxy.x() if proxy is not None else 0.0
            left = max(bounding.left(), viewport[0] - offset)
            right = min(bounding.right(), viewport[1] - offset)
            if right - left < 1:
                return bounding.left(), bounding.right()
            return left, right
        except Exception:
            return bounding.left(), bounding.right()

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paint(self, painter, option, widget=None):
        try:
            self._paint(painter)
        except Exception as exc:
            # Never let an exception escape paint() — Qt leaves QPainter
            # in a half-active state if we do, which cascades into stray
            # warnings, mismatched begin/end pairs, and segfaults on the
            # next repaint.  Log via stdout (visible in dev) and bail.
            print(f"[audiowave] paint failed: {exc!r}")

    def _paint(self, painter):
        wf = self.element.waveform_component
        height = self.element.height
        bounding = self.boundingRect()
        if bounding.width() <= 0 or height <= 0:
            return

        if wf is None or not wf.is_ready or not wf.lod_min:
            self._paint_loading(painter, bounding, height)
            return

        bounds = self._data_x_bounds(wf)
        if bounds is None:
            return
        data_x_left, data_x_right = bounds
        playback_width = data_x_right - data_x_left
        if playback_width <= 0:
            return

        x_left_vis, x_right_vis = self._visible_x_range(bounding)
        # Clip the visible window to the actual data area.  We use scene
        # x positions directly (not visible-range pixel indices) so that
        # the same audio time always lands on the same pixel column,
        # regardless of the current scroll offset.
        x_left = max(x_left_vis, data_x_left)
        x_right = min(x_right_vis, data_x_right)
        if x_right - x_left < 1:
            return

        base_fpp = max(1, wf.frames_per_peak)
        # Frames-per-pixel computed from the absolute zoom (i.e. the
        # scene's playback area), not from the visible slice — keeps the
        # LOD level stable across scroll.
        frames_per_pixel = wf.total_frames / playback_width
        peaks_per_pixel = frames_per_pixel / base_fpp

        n_levels = len(wf.lod_min)
        if peaks_per_pixel <= 1.0:
            level = 0
        else:
            level = min(n_levels - 1, max(0, int(math.log2(peaks_per_pixel))))

        lod_mins = wf.lod_min[level]
        lod_maxs = wf.lod_max[level]
        n_peaks = lod_mins.shape[0]
        if n_peaks == 0:
            return
        level_fpp = base_fpp * (1 << level)

        mid = height / 2.0
        color = QColor(settings.get("audiowave_timeline", "default_color"))
        pen = QPen(color)
        pen.setWidth(0)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)

        self._paint_aggregated_bars(
            painter,
            lod_mins,
            lod_maxs,
            n_peaks,
            level_fpp,
            playback_width,
            wf.total_frames,
            data_x_left,
            x_left,
            x_right,
            mid,
        )

    # ------------------------------------------------------------------
    # Drawing modes
    # ------------------------------------------------------------------

    def _paint_aggregated_bars(
        self,
        painter,
        lod_mins: np.ndarray,
        lod_maxs: np.ndarray,
        n_peaks: int,
        level_fpp: int,
        playback_width: float,
        total_frames: int,
        data_x_left: float,
        x_left: float,
        x_right: float,
        mid: float,
    ) -> None:
        """Per-pixel min/max aggregation drawn as vertical bars.

        Used when there is at least one stored peak per pixel column.
        """
        # Snap to integer scene-x positions — that's what makes scrolling
        # stable: every absolute pixel column always reduces over the same
        # peak slice.
        ix_left = int(math.floor(x_left))
        ix_right = int(math.ceil(x_right))
        if ix_right <= ix_left:
            return
        n_pixels = ix_right - ix_left

        pixel_xs = np.arange(ix_left, ix_right + 1, dtype=np.float64)
        # Scene-x → audio frame, anchored to the absolute time axis.
        rel = (pixel_xs - data_x_left) / playback_width
        np.clip(rel, 0.0, 1.0, out=rel)
        pixel_frame_f = rel * total_frames
        pixel_peak_f = pixel_frame_f / level_fpp

        starts = np.floor(pixel_peak_f[:-1]).astype(np.int64)
        ends = np.ceil(pixel_peak_f[1:]).astype(np.int64)
        # ``reduceat`` requires every index be strictly < len(a); clip to
        # n_peaks - 1.  This may drop the very last peak from the right-most
        # column when the viewport extends to the audio's end — visually
        # imperceptible, and worth it for correctness/safety.
        np.clip(starts, 0, n_peaks - 1, out=starts)
        np.clip(ends, 1, n_peaks - 1, out=ends)
        # Force the boundary array to be non-decreasing — if the last
        # window is degenerate, reduceat handles equal/decreasing indices
        # by yielding the single value at that index.
        idx = np.empty(n_pixels + 1, dtype=np.int64)
        idx[:-1] = starts
        idx[-1] = max(int(ends[-1]), int(starts[-1]))
        idx[-1] = min(idx[-1], n_peaks - 1)

        col_min = np.minimum.reduceat(lod_mins, idx)[:n_pixels]
        col_max = np.maximum.reduceat(lod_maxs, idx)[:n_pixels]

        y_top = mid - col_max * mid
        y_bot = mid - col_min * mid

        # Build line segments for one batched draw call.
        lines = [
            QLineF(
                QPointF(float(pixel_xs[i]) + 0.5, float(y_top[i])),
                QPointF(float(pixel_xs[i]) + 0.5, float(y_bot[i])),
            )
            for i in range(n_pixels)
        ]
        painter.drawLines(lines)

    def _paint_loading(self, painter, bounding: QRectF, height: float) -> None:
        # Center inside the data area, intersected with the visible viewport,
        # so a long file scrolled mostly off-screen still puts the spinner
        # somewhere the user can see it.
        wf = self.element.waveform_component
        x_left, x_right = self._visible_x_range(bounding)
        if wf is not None:
            data_bounds = self._data_x_bounds(wf)
            if data_bounds is not None:
                x_left = max(x_left, data_bounds[0])
                x_right = min(x_right, data_bounds[1])
        if x_right <= x_left or height <= 0:
            return

        self.start_spinner()

        cx = (x_left + x_right) / 2.0
        cy = height / 2.0
        diameter = max(
            self.LOADING_SPINNER_MIN_DIAMETER,
            min(self.LOADING_SPINNER_MAX_DIAMETER, height * 0.4),
        )
        rect = QRectF(
            cx - diameter / 2, cy - diameter / 2, diameter, diameter
        )

        accent = QColor(settings.get("audiowave_timeline", "default_color"))
        pen_width = max(2.0, diameter / 10.0)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        track_color = QColor(accent)
        track_color.setAlpha(60)
        track_pen = QPen(track_color)
        track_pen.setWidthF(pen_width)
        track_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0, 360 * 16)

        seg_pen = QPen(accent)
        seg_pen.setWidthF(pen_width)
        seg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(seg_pen)
        painter.drawArc(
            rect,
            int(-self._spinner_angle * 16),
            int(self.LOADING_SPINNER_ARC_DEG * 16),
        )
        painter.restore()
