"""The window with the table of note groups: every group's pitch-class set, for
comparing them. Sorting by prime form puts groups of one set class together.

It's a window of its own so that opening it leaves the score its full width.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QHideEvent, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tilia.requests import Get, get
from tilia.timelines.score.pcset import PitchClassSetAnalysis
from tilia.ui import commands
from tilia.ui.windows.score.group_panel import (
    format_pcs,
    format_prime_form,
    format_vector,
)
from tilia.ui.windows.view_window import ViewWidget

COLUMNS = [
    ("Group", "The group's name and color."),
    ("Measure", "Where the group's notes are first played."),
    ("Prime form", "Sorts by cardinality, and then by pitch class."),
    ("Forte", "Only for sets that also exist in 12 notes to the octave."),
    ("Cardinality", "How many pitch classes the set has."),
    ("Normal form", "The set's most compact ordering."),
    ("Pitch classes", "In quarter tones, at sounding pitch, with 0 on C."),
    ("Interval-class vector", "Counts classes 1 to 12, written in hexadecimal."),
]
MEASURE_COLUMN = 1
INITIAL_WIDTH = 760
INITIAL_HEIGHT = 300


@dataclass(frozen=True)
class GroupRow:
    group_id: str
    label: str
    color: str | None
    analysis: PitchClassSetAnalysis
    measures: str
    # When the group's notes are first played, which orders the measures column.
    start: float
    end: float


class _Item(QTableWidgetItem):
    """Sorts by a key of its own: "10" comes after "9", and (0 1 2) after (0 3)."""

    def __init__(self, text: str, sort_key: Any) -> None:
        super().__init__(text)
        self.sort_key = sort_key

    def __lt__(self, other: QTableWidgetItem) -> bool:
        return self.sort_key < other.sort_key


def _forte_key(name: str | None) -> tuple[int, ...]:
    # Numbers only, for 4-Z15 to sit between 4-14 and 4-16. Sets with no name last.
    return tuple(int(n) for n in re.findall(r"\d+", name)) if name else (99,)


def _items(row: GroupRow) -> list[_Item]:
    analysis = row.analysis
    cardinality = analysis.cardinality
    return [
        _Item(row.label, row.label.casefold()),
        _Item(row.measures, (row.start, row.end)),
        _Item(format_prime_form(analysis), (cardinality, analysis.prime_form)),
        _Item(analysis.forte_name or "", _forte_key(analysis.forte_name)),
        _Item(str(cardinality), cardinality),
        _Item(
            f"[{format_pcs(analysis.normal_form)}]",
            (cardinality, analysis.normal_form),
        ),
        _Item(
            f"{{{format_pcs(analysis.pitch_classes)}}}",
            (cardinality, analysis.pitch_classes),
        ),
        _Item(
            format_vector(analysis),
            analysis.interval_class_vector,
        ),
    ]


class GroupTable(QTableWidget):
    def __init__(self, timeline_id: str, parent: QWidget | None = None) -> None:
        super().__init__(0, len(COLUMNS), parent)
        self.timeline_id = timeline_id

        for column, (title, tooltip) in enumerate(COLUMNS):
            header = QTableWidgetItem(title)
            header.setToolTip(tooltip)
            self.setHorizontalHeaderItem(column, header)
        self.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.horizontalHeader().setSortIndicator(
            MEASURE_COLUMN, Qt.SortOrder.AscendingOrder
        )
        self.verticalHeader().hide()
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.itemSelectionChanged.connect(self._on_selection_changed)

    def group_id_at(self, row: int) -> str:
        return self.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def selected_group_id(self) -> str | None:
        rows = self.selectionModel().selectedRows()
        return self.group_id_at(rows[0].row()) if rows else None

    def show_groups(self, rows: list[GroupRow], active_group: str | None) -> None:
        scroll = self.verticalScrollBar().value()
        self.blockSignals(True)
        self.setSortingEnabled(False)
        self.setRowCount(len(rows))
        for index, row in enumerate(rows):
            items = _items(row)
            items[0].setData(Qt.ItemDataRole.UserRole, row.group_id)
            if row.color:
                items[0].setData(Qt.ItemDataRole.DecorationRole, QColor(row.color))
            for column, item in enumerate(items):
                self.setItem(index, column, item)
        # Sorts again, by the column the table was sorted by.
        self.setSortingEnabled(True)
        self.blockSignals(False)
        self.verticalScrollBar().setValue(scroll)
        self.select_group(active_group)

    def select_group(self, group_id: str | None) -> None:
        if group_id == self.selected_group_id():
            return
        self.blockSignals(True)
        self.clearSelection()
        for row in range(self.rowCount()):
            if self.group_id_at(row) == group_id:
                self.selectRow(row)
                self.scrollToItem(self.item(row, 0))
                break
        self.blockSignals(False)

    def write_csv(self, path: Path) -> None:
        """Writes the table as it reads, in its current order."""
        # With the BOM, Excel doesn't garble the dash in a range of measures.
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(title for title, _ in COLUMNS)
            for row in range(self.rowCount()):
                writer.writerow(
                    self.item(row, column).text() for column in range(len(COLUMNS))
                )

    def _on_selection_changed(self) -> None:
        if group_id := self.selected_group_id():
            commands.execute(
                "timeline.score.group.select",
                group_id=group_id,
                timeline_id=self.timeline_id,
            )


class GroupTableWindow(ViewWidget, QDialog):
    def __init__(
        self,
        timeline_id: str,
        score_name: str,
        on_visibility_changed: Callable[[bool], Any],
    ) -> None:
        title = f"Note groups: {score_name}"
        super().__init__(title, get(Get.MAIN_WINDOW), menu_title=title)
        self.setWindowTitle(title)
        self.resize(INITIAL_WIDTH, INITIAL_HEIGHT)
        self._on_visibility_changed = on_visibility_changed
        self.table = GroupTable(timeline_id, self)
        self.export_button = QPushButton("Export CSV")
        self.export_button.setToolTip("Save the table to a CSV file, as it is sorted")
        self.export_button.setEnabled(False)
        self.export_button.setAutoDefault(False)
        self.export_button.clicked.connect(
            lambda: commands.execute(
                "timeline.score.group.export_table", timeline_id=timeline_id
            )
        )
        buttons = QHBoxLayout()
        buttons.setContentsMargins(4, 4, 4, 4)
        buttons.addStretch()
        buttons.addWidget(self.export_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.table)
        layout.addLayout(buttons)

    def show_groups(self, rows: list[GroupRow], active_group: str | None) -> None:
        self.table.show_groups(rows, active_group)
        self.export_button.setEnabled(bool(rows))

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._on_visibility_changed(True)

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self._on_visibility_changed(False)

    def reject(self) -> None:
        # Escape closes it as the window's close button does.
        self.close()
