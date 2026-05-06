from __future__ import annotations

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItemGroup, QGraphicsLineItem, QGraphicsRectItem

from tilia.ui.timelines.cursors import CursorMixIn


class RangeBodyHandle(CursorMixIn, QGraphicsRectItem):
    def __init__(
        self, x: float, width: int, height: int, y_pos: float, color: str = "black"
    ):
        super().__init__(cursor_shape=Qt.CursorShape.SizeHorCursor)
        self._color = color
        self.set_position(x, width, height, y_pos)
        self.set_fill(color)
        self.set_pen_style_no_pen()

    def set_fill(self, color: str) -> None:
        self._color = color
        self.setBrush(QColor(color))

    def set_transparent(self, transparent: bool) -> None:
        # Used at joined edges so the dashed join separator is visible while
        # the handle stays clickable. We use a fully-transparent brush rather
        # than NoBrush so the rect's interior still participates in
        # hit-testing — with NoBrush, Qt's QGraphicsScene treats the unfilled
        # interior as click-through, and the click falls to the body
        # underneath, starting a rubber-band selection instead of a drag.
        if transparent:
            color = QColor(self._color)
            color.setAlpha(0)
            self.setBrush(color)
        else:
            self.setBrush(QColor(self._color))

    def set_pen_style_no_pen(self) -> None:
        pen = QPen(QColor("black"))
        pen.setStyle(Qt.PenStyle.NoPen)
        self.setPen(pen)

    def set_position(self, x: float, width: int, height: int, y_pos: float) -> None:
        self.setRect(self.get_rect(x, width, height, y_pos))
        self.setZValue(10)

    @staticmethod
    def get_rect(x: float, width: int, height: int, y_pos: float) -> QRectF:
        return QRectF(
            QPointF(x - (width / 2), y_pos - height),
            QPointF(x + (width / 2), y_pos),
        )


class RangeFrameHandle(QGraphicsItemGroup):
    """Whisker shown for pre_start / post_end. A dashed horizontal line
    runs from the body extremity to the frame extremity at the row's
    vertical centre, with a short vertical line at the far end serving
    as the drag handle."""

    VERTICAL_LINE_WIDTH = 3
    HORIZONTAL_LINE_WIDTH = 1
    HEIGHT = 10

    def __init__(self, body_x: float, frame_x: float, y: float):
        super().__init__()
        self.horizontal_line = self.HLine(
            body_x, frame_x, y, self.HORIZONTAL_LINE_WIDTH
        )
        self.vertical_line = self.VLine(
            frame_x,
            y - self.HEIGHT / 2,
            y + self.HEIGHT / 2,
            self.VERTICAL_LINE_WIDTH,
        )
        self.addToGroup(self.horizontal_line)
        self.addToGroup(self.vertical_line)
        # By default, QGraphicsItemGroup intercepts events targeted at its
        # children, which prevents the VLine's CursorMixIn from receiving
        # hover events. Disabling this lets each child handle its own
        # events (cursor change, drag).
        self.setHandlesChildEvents(False)
        # Above the body so the dashed line and grab-tab read on top of
        # the range fill.
        self.setZValue(15)
        self.setVisible(False)

    def set_position(self, body_x: float, frame_x: float, y: float) -> None:
        self.horizontal_line.set_position(body_x, frame_x, y)
        self.vertical_line.set_position(
            frame_x, y - self.HEIGHT / 2, y + self.HEIGHT / 2
        )

    class VLine(CursorMixIn, QGraphicsLineItem):
        # Hover/click hit area widened beyond the rendered pen so the
        # cursor changes and the line is grabbable without pixel-perfect
        # aim. Qt's default `shape()` for a 3-px line returns a region
        # only 3 px wide.
        HIT_WIDTH = 8

        def __init__(self, x: float, y0: float, y1: float, width: int):
            super().__init__(cursor_shape=Qt.CursorShape.SizeHorCursor)
            self.set_position(x, y0, y1)
            self.set_pen(width)

        def set_pen(self, width: int) -> None:
            pen = QPen(QColor("black"))
            pen.setStyle(Qt.PenStyle.SolidLine)
            pen.setWidth(width)
            self.setPen(pen)

        def set_position(self, x: float, y0: float, y1: float) -> None:
            self.setLine(QLineF(x, y0, x, y1))

        def shape(self) -> QPainterPath:
            line = self.line()
            half = self.HIT_WIDTH / 2
            rect = QRectF(
                QPointF(line.x1() - half, min(line.y1(), line.y2())),
                QPointF(line.x2() + half, max(line.y1(), line.y2())),
            )
            path = QPainterPath()
            path.addRect(rect)
            return path

        def boundingRect(self) -> QRectF:
            return self.shape().boundingRect()

    class HLine(QGraphicsLineItem):
        def __init__(self, x0: float, x1: float, y: float, width: int):
            super().__init__()
            self.set_position(x0, x1, y)
            self.set_pen(width)
            # Non-interactive: clicks should fall through to the timeline
            # so click-to-select and rubber-band selection both still
            # work on the ranges underneath.
            self.ignore_right_click = True

        def set_pen(self, width: int) -> None:
            pen = QPen(QColor("black"))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidth(width)
            self.setPen(pen)

        def set_position(self, x0: float, x1: float, y: float) -> None:
            self.setLine(QLineF(x0, y, x1, y))
