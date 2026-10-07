"""
A scrollable table previewing what a typed pattern expands to, with a footer
about how it repeats. Used by the beat pattern and beat unit dialogs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

# The table scrolls past this height rather than growing the dialog.
MAX_TABLE_HEIGHT = 160
HIGHLIGHT_COLOR = QColor("#ffe2b3")


@dataclass(frozen=True)
class PreviewContent:
    headers: list[str] = field(default_factory=list)
    rows: list[tuple[str, ...]] = field(default_factory=list)
    footer: str = ""
    # Shown instead of the table, e.g. while the pattern is half-typed.
    error: str = ""
    highlighted_rows: frozenset[int] = frozenset()


class PatternPreview(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(self)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setMaximumHeight(MAX_TABLE_HEIGHT)

        self.footer = QLabel(self)
        self.footer.setTextFormat(Qt.TextFormat.PlainText)
        self.footer.setWordWrap(True)

        self.error = QLabel(self)
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)

        self.layout().addWidget(self.table)
        self.layout().addWidget(self.footer)
        self.layout().addWidget(self.error)

    def set_content(self, content: PreviewContent) -> None:
        self.error.setText(content.error)
        self.error.setVisible(bool(content.error))
        self.table.setVisible(not content.error)
        self.footer.setVisible(not content.error)
        if content.error:
            return

        self.table.clear()
        self.table.setColumnCount(len(content.headers))
        self.table.setHorizontalHeaderLabels(content.headers)
        self.table.setRowCount(len(content.rows))
        for row_index, row in enumerate(content.rows):
            for column_index, text in enumerate(row):
                item = QTableWidgetItem(text)
                if row_index in content.highlighted_rows:
                    item.setBackground(HIGHLIGHT_COLOR)
                self.table.setItem(row_index, column_index, item)
        self.footer.setText(content.footer)

    def rows(self) -> list[tuple[str, ...]]:
        return [
            tuple(
                self.table.item(row, column).text()
                for column in range(self.table.columnCount())
            )
            for row in range(self.table.rowCount())
        ]

    def highlighted_rows(self) -> set[int]:
        return {
            row
            for row in range(self.table.rowCount())
            if self.table.item(row, 0).background().color() == HIGHLIGHT_COLOR
        }
