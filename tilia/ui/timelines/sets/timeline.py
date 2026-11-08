from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPen
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
)

from tilia.requests import Get, Post, get, listen
from tilia.settings import settings
from tilia.timelines.component_kinds import ComponentKind
from tilia.timelines.score.timeline import ScoreTimeline
from tilia.timelines.sets.timeline import SetsTimeline
from tilia.ui import commands
from tilia.ui.coords import time_x_converter
from tilia.ui.timelines.base.element_manager import ElementManager
from tilia.ui.timelines.base.timeline import TimelineUI
from tilia.ui.timelines.cursors import CursorMixIn
from tilia.ui.windows.score.group_panel import format_prime_form

if TYPE_CHECKING:
    from tilia.timelines.score.components.note_group import NoteGroup
    from tilia.ui.timelines.collection.collection import TimelineUIs
    from tilia.ui.timelines.scene import TimelineScene
    from tilia.ui.timelines.view import TimelineView

BAR_GAP = 1
TEXT_LEFT_PADDING = 3
MIN_BAR_WIDTH = 2
LIGHTNESS_OF_DARK_COLORS = 0.5


@dataclass(frozen=True)
class SetSpan:
    group_id: str
    timeline_id: str
    start: float
    end: float
    text: str
    color: str


def _get_text(group: NoteGroup) -> str:
    analysis = group.analysis
    prime_form = format_prime_form(analysis) if analysis.pitch_classes else ""
    # The prime form first: a short bar cuts off the end of its text.
    return f"{prime_form} {group.label}".strip()


def get_set_spans() -> list[SetSpan]:
    spans = []
    for timeline in get(Get.TIMELINE_COLLECTION).get_timelines_by_type(ScoreTimeline):
        for component in timeline.components:
            if component.KIND != ComponentKind.NOTE_GROUP:
                continue
            span = timeline.get_elements_span(component.element_ids)
            if span:
                spans.append(
                    SetSpan(
                        component.id,
                        timeline.id,
                        *span,
                        _get_text(component),
                        component.color
                        or settings.get("sets_timeline", "default_color"),
                    )
                )
    return spans


def arrange_in_rows(spans: list[SetSpan]) -> list[list[SetSpan]]:
    """Each span goes on the first row that is free when it starts, so that
    groups sounding together, such as the voice's and the piano's, stack."""
    rows: list[list[SetSpan]] = []
    for span in sorted(spans, key=lambda s: (s.start, s.end)):
        for row in rows:
            if row[-1].end <= span.start:
                row.append(span)
                break
        else:
            rows.append([span])
    return rows


class SetBar(CursorMixIn, QGraphicsRectItem):
    def __init__(self, span: SetSpan, rect: QRectF):
        super().__init__(cursor_shape=Qt.CursorShape.PointingHandCursor)
        self.span = span
        self.setPos(rect.topLeft())
        self.setRect(QRectF(0, 0, rect.width(), rect.height()))
        color = QColor(span.color)
        self.setBrush(QBrush(color))
        self.setPen(QPen(color.darker(130)))
        self.setToolTip(span.text)
        # Behind the playback line.
        self.setZValue(-1)
        # A short bar shows as much of its text as fits.
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape)
        self._setup_text(color, rect.height())

    def _setup_text(self, background: QColor, height: float) -> None:
        self.text = QGraphicsSimpleTextItem(self.span.text, self)
        self.text.setBrush(
            QBrush(
                Qt.GlobalColor.white
                if background.lightnessF() < LIGHTNESS_OF_DARK_COLORS
                else Qt.GlobalColor.black
            )
        )
        text_height = self.text.boundingRect().height()
        self.text.setPos(TEXT_LEFT_PADDING, (height - text_height) / 2)


class SetsTimelineUI(TimelineUI):
    TOOLBAR_CLASS = None
    CONTEXT_MENU_CLASS = []
    timeline_class = SetsTimeline

    def __init__(
        self,
        id: int,
        collection: TimelineUIs,
        element_manager: ElementManager,
        scene: TimelineScene,
        view: TimelineView,
    ):
        super().__init__(
            id=id,
            collection=collection,
            element_manager=element_manager,
            scene=scene,
            view=view,
        )
        self.bars: list[SetBar] = []

        listen(self, Post.SCORE_NOTE_GROUPS_CHANGED, self.redraw)
        listen(self, Post.SCORE_TIMELINE_COMPONENTS_DESERIALIZED, self.on_score_change)
        listen(self, Post.SCORE_TIMELINE_CLEAR_DONE, self.on_score_change)
        listen(self, Post.TIMELINE_DELETE_DONE, self.on_timeline_deleted)
        listen(self, Post.TIMELINES_SCALE_DONE, self.redraw)
        listen(self, Post.SETTINGS_UPDATED, self.on_settings_updated)

        # The collection doesn't know this timeline UI yet, so it couldn't handle
        # the height being set through it.
        height = self._draw()
        self.timeline.set_data("height", height)
        self.scene.set_height(height)
        self.view.set_height(height)

    @property
    def row_height(self) -> int:
        return settings.get("sets_timeline", "row_height")

    def _draw(self) -> int:
        """Returns the height the bars need."""
        for bar in self.bars:
            self.scene.removeItem(bar)
        self.bars = []

        rows = arrange_in_rows(get_set_spans())
        for row_index, row in enumerate(rows):
            for span in row:
                self.bars.append(SetBar(span, self._get_bar_rect(span, row_index)))
                self.scene.addItem(self.bars[-1])
        return max(len(rows), 1) * self.row_height

    def _get_bar_rect(self, span: SetSpan, row_index: int) -> QRectF:
        x0 = time_x_converter.get_x_by_time(span.start)
        x1 = time_x_converter.get_x_by_time(span.end)
        return QRectF(
            x0,
            row_index * self.row_height + BAR_GAP,
            max(x1 - x0, MIN_BAR_WIDTH),
            self.row_height - 2 * BAR_GAP,
        )

    def redraw(self) -> None:
        height = self._draw()
        get(Get.TIMELINE_COLLECTION).set_timeline_data(self.id, "height", height)

    def on_score_change(self, *_) -> None:
        self.redraw()

    def on_timeline_deleted(self, id: int) -> None:
        if id != self.id:
            self.redraw()

    def on_settings_updated(self, updated_settings: list[str]) -> None:
        if "sets_timeline" in updated_settings:
            self.redraw()

    def set_width(self, width: int) -> None:
        super().set_width(width)
        self._draw()

    def on_left_click(
        self,
        item: QGraphicsItem | None,
        modifier: Qt.KeyboardModifier,
        double: bool,
        x: int,
        y: int,
    ) -> None:
        if isinstance(item, QGraphicsSimpleTextItem):
            item = item.parentItem()
        if not isinstance(item, SetBar):
            return

        commands.execute(
            "timeline.score.group.select",
            group_id=item.span.group_id,
            timeline_id=item.span.timeline_id,
        )
        if double:
            commands.execute("media.seek", item.span.start)
        elif modifier != Qt.KeyboardModifier.AltModifier:
            commands.execute("media.seek", item.span.start, seek_if_playing=False)

    def __str__(self) -> str:
        return "Sets Timeline"
