"""The window with the table of note groups: every group's pitch-class set, for
comparing them. Sorting by prime form puts groups of one set class together, and
selecting several rows shows the operations that relate those groups.

It's a window of its own so that opening it leaves the score its full width.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QItemSelectionModel, Qt, Signal
from PySide6.QtGui import QColor, QHideEvent, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tilia.requests import Get, get
from tilia.timelines.score.pcset import (
    PitchClassSetAnalysis,
    inversions,
    transpositions,
)
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
RELATION_COLUMNS = [
    ("From", "The group the operation applies to, the earlier in the score."),
    ("To", "The group the operation gives."),
    (
        "Transposition",
        "Tn adds n to each pitch class. n is in quarter tones," " so T2 is a semitone.",
    ),
    (
        "Inversion",
        "In takes each pitch class to n minus it, so I0 inverts about C.",
    ),
]
MEASURE_COLUMN = 1
INITIAL_WIDTH = 760
INITIAL_HEIGHT = 460
# The pairs grow with the square of the groups, and a table of thousands is slow.
MAX_GROUPS_RELATED = 30
RELATIONS_HINT = (
    "Select two or more rows to see how they relate"
    " (Ctrl-click, or Cmd-click on macOS)."
)
TOO_MANY_RELATED_HINT = (
    f"Select at most {MAX_GROUPS_RELATED} rows to see how they relate."
)


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


def _set_headers(table: QTableWidget, columns: list[tuple[str, str]]) -> None:
    for column, (title, tooltip) in enumerate(columns):
        header = QTableWidgetItem(title)
        header.setToolTip(tooltip)
        table.setHorizontalHeaderItem(column, header)
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.ResizeToContents
    )


def _format_operations(name: str, operations: tuple[int, ...]) -> str:
    return ", ".join(f"{name}{n}" for n in operations) or "none"


def _group_item(row: GroupRow) -> QTableWidgetItem:
    """Names a group, which may have no label, by where it is and its notes."""
    place = f"m. {row.measures}" if row.measures else ""
    pcs = f"{{{format_pcs(row.analysis.pitch_classes)}}}"
    text = " ".join(part for part in (place, pcs) if part)
    item = QTableWidgetItem(f"{row.label}, {text}" if row.label else text)
    if row.color:
        item.setData(Qt.ItemDataRole.DecorationRole, QColor(row.color))
    return item


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
    selected_groups_changed = Signal()

    def __init__(self, timeline_id: str, parent: QWidget | None = None) -> None:
        super().__init__(0, len(COLUMNS), parent)
        self.timeline_id = timeline_id
        self._rows: dict[str, GroupRow] = {}

        _set_headers(self, COLUMNS)
        self.horizontalHeader().setSortIndicator(
            MEASURE_COLUMN, Qt.SortOrder.AscendingOrder
        )
        self.verticalHeader().hide()
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.cellClicked.connect(self._on_cell_clicked)

    def group_id_at(self, row: int) -> str:
        return self.item(row, 0).data(Qt.ItemDataRole.UserRole)

    def selected_group_ids(self) -> list[str]:
        return [
            self.group_id_at(index.row())
            for index in self.selectionModel().selectedRows()
        ]

    def selected_group_id(self) -> str | None:
        """The selected group, if it's only one."""
        ids = self.selected_group_ids()
        return ids[0] if len(ids) == 1 else None

    def selected_rows(self) -> list[GroupRow]:
        """The selected groups, in score order."""
        ids = set(self.selected_group_ids())
        rows = [row for id, row in self._rows.items() if id in ids]
        return sorted(rows, key=lambda row: (row.start, row.end))

    def show_groups(self, rows: list[GroupRow], active_group: str | None) -> None:
        selected = self.selected_group_ids()
        self._rows = {row.group_id: row for row in rows}
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
        # Rows being compared stay selected unless another group was made active.
        # The score hasn't heard yet when the active group was just deleted.
        if active_group not in self._rows:
            active_group = None
        kept = [id for id in selected if id in self._rows]
        if len(kept) > 1 and (active_group is None or active_group in kept):
            self._set_selection(kept)
        else:
            self._set_selection([])
            self.select_group(active_group)
        self.selected_groups_changed.emit()

    def select_group(self, group_id: str | None) -> None:
        selected = self.selected_group_ids()
        if group_id in selected or (group_id is None and not selected):
            return
        self._set_selection([] if group_id is None else [group_id])
        for row in range(self.rowCount()):
            if self.group_id_at(row) == group_id:
                self.scrollToItem(self.item(row, 0))
                # Shift-clicking then extends the selection from this row.
                self.selectionModel().setCurrentIndex(
                    self.model().index(row, 0),
                    QItemSelectionModel.SelectionFlag.NoUpdate,
                )
                break
        self.selected_groups_changed.emit()

    def _set_selection(self, group_ids: list[str]) -> None:
        """Doesn't run any command: the score already shows these groups."""
        self.blockSignals(True)
        self.clearSelection()
        for row in range(self.rowCount()):
            if self.group_id_at(row) in group_ids:
                self.selectionModel().select(
                    self.model().index(row, 0),
                    QItemSelectionModel.SelectionFlag.Select
                    | QItemSelectionModel.SelectionFlag.Rows,
                )
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

    def _on_cell_clicked(self) -> None:
        if group_id := self.selected_group_id():
            commands.execute(
                "timeline.score.group.audition",
                group_id=group_id,
                timeline_id=self.timeline_id,
            )

    def _on_selection_changed(self) -> None:
        if group_id := self.selected_group_id():
            commands.execute(
                "timeline.score.group.select",
                group_id=group_id,
                timeline_id=self.timeline_id,
            )
        self.selected_groups_changed.emit()


class RelationTable(QTableWidget):
    """How each pair of selected groups relates. Computed, so it can't go stale
    when a group's notes change."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, len(RELATION_COLUMNS), parent)
        _set_headers(self, RELATION_COLUMNS)
        self.verticalHeader().hide()
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def show_relations(self, rows: list[GroupRow]) -> None:
        pairs = list(combinations(rows, 2))
        self.setRowCount(len(pairs))
        for index, (source, target) in enumerate(pairs):
            pcs = (source.analysis.pitch_classes, target.analysis.pitch_classes)
            self.setItem(index, 0, _group_item(source))
            self.setItem(index, 1, _group_item(target))
            self.setItem(
                index,
                2,
                QTableWidgetItem(_format_operations("T", transpositions(*pcs))),
            )
            self.setItem(
                index, 3, QTableWidgetItem(_format_operations("I", inversions(*pcs)))
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
        self.table.selected_groups_changed.connect(self._show_relations)
        self.relations_hint = QLabel(RELATIONS_HINT)
        self.relations_hint.setContentsMargins(4, 4, 4, 4)
        self.relations = RelationTable(self)
        self.relations.hide()
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
        layout.addWidget(self.table, 3)
        layout.addWidget(self.relations_hint)
        layout.addWidget(self.relations, 2)
        layout.addLayout(buttons)

    def show_groups(self, rows: list[GroupRow], active_group: str | None) -> None:
        self.table.show_groups(rows, active_group)
        self.export_button.setEnabled(bool(rows))

    def _show_relations(self) -> None:
        rows = self.table.selected_rows()
        can_relate = 2 <= len(rows) <= MAX_GROUPS_RELATED
        self.relations.show_relations(rows if can_relate else [])
        if not can_relate:
            self.relations_hint.setText(
                TOO_MANY_RELATED_HINT
                if len(rows) > MAX_GROUPS_RELATED
                else RELATIONS_HINT
            )
        self.relations.setVisible(can_relate)
        self.relations_hint.setVisible(not can_relate)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._on_visibility_changed(True)

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self._on_visibility_changed(False)

    def reject(self) -> None:
        # Escape closes it as the window's close button does.
        self.close()
