"""
The dialog where a beat timeline's bars are written: a pattern of time
signatures on one line (see `tilia.timelines.beat.pattern`), and a table of
the bars it makes over the tapped beats, where each row's bar numbers, time
signature and taps can be edited. Editing a row rewrites the pattern, and
editing the pattern rewrites the rows.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QKeyEvent, QValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

import tilia.ui.strings
from tilia.requests import Get, get
from tilia.timelines.beat.pattern import (
    PlannedBar,
    format_planned_bar,
    format_planned_bars,
    parse,
)
from tilia.timelines.beat.units import parse_units

_PATTERN_CHARACTERS = set("0123456789[]/+()")
# The table scrolls past this height rather than growing the dialog.
MAX_TABLE_HEIGHT = 240
CHANGED_COLOR = QColor("#ffe2b3")
UNTAPPED_COLOR = QColor("gray")
BARS_COLUMN, TIME_SIGNATURE_COLUMN, TAPS_COLUMN = range(3)


class BeatPatternValidator(QValidator):
    """
    Blocks characters that can never be part of a pattern, and reports text
    that could still become valid as Intermediate so the user can keep typing.
    """

    def validate(self, text: str, pos: int) -> tuple[QValidator.State, str, int]:
        if any(c not in _PATTERN_CHARACTERS and not c.isspace() for c in text):
            return QValidator.State.Invalid, text, pos
        if parse(text).is_complete:
            return QValidator.State.Acceptable, text, pos
        return QValidator.State.Intermediate, text, pos


class PatternLineEdit(QLineEdit):
    """
    Pairs brackets as they are typed: "[" inserts "[]" with the cursor
    between them (or wraps the selection), "]" steps over a closing bracket
    that is already there, and Backspace between an empty pair removes both.
    """

    def keyPressEvent(self, event: QKeyEvent) -> None:
        text = self.text()
        cursor = self.cursorPosition()

        if event.text() == "[":
            if self.hasSelectedText():
                start = self.selectionStart()
                selected = self.selectedText()
                self.insert(f"[{selected}]")
                self.setCursorPosition(start + len(selected) + 2)
            else:
                self.insert("[]")
                self.setCursorPosition(cursor + 1)
            return

        if (
            event.text() == "]"
            and not self.hasSelectedText()
            and text[cursor : cursor + 1] == "]"
        ):
            self.setCursorPosition(cursor + 1)
            return

        if (
            event.key() == Qt.Key.Key_Backspace
            and not self.hasSelectedText()
            and cursor > 0
            and text[cursor - 1 : cursor + 1] == "[]"
        ):
            self.setText(text[: cursor - 1] + text[cursor + 1 :])
            self.setCursorPosition(cursor - 1)
            return

        super().keyPressEvent(event)


@dataclass(frozen=True)
class BarsEdit:
    """What the dialog was left with: the pattern, and the number of each
    bar the tapped beats fill."""

    pattern: str
    numbers: list[int]


@dataclass(frozen=True)
class BarRow:
    """Consecutive bars that are alike. `start` is a 0-based bar index."""

    start: int
    bar: PlannedBar
    numbers: tuple[int, ...]
    is_tapped: bool

    @property
    def count(self) -> int:
        return len(self.numbers)


def lay_out(planned: list[PlannedBar], beat_count: int) -> tuple[list[PlannedBar], int]:
    """
    The bars `planned` makes over `beat_count` beats, repeating it from its
    start as often as the beats need, then the rest of it; and how many of
    them the beats reach.
    """
    bars: list[PlannedBar] = []
    beats = 0
    while beats < beat_count:
        bar = planned[len(bars) % len(planned)]
        bars.append(bar)
        beats += bar.beat_count
    tapped = len(bars)
    return bars + planned[tapped:], tapped


def get_numbers(count: int, overrides: dict[int, int]) -> list[int]:
    """Bar numbers, counting on from the bar before where none is set."""
    numbers: list[int] = []
    for index in range(count):
        default = numbers[-1] + 1 if numbers else 1
        numbers.append(overrides.get(index, default))
    return numbers


def get_overrides(numbers: list[int]) -> dict[int, int]:
    """The numbers that don't count on from the bar before (or from 1)."""
    return {
        index: number
        for index, number in enumerate(numbers)
        if number != (numbers[index - 1] + 1 if index else 1)
    }


def get_rows(bars: list[PlannedBar], tapped: int, numbers: list[int]) -> list[BarRow]:
    """Groups consecutive bars that are alike and numbered one after another."""
    rows: list[BarRow] = []
    for index, (bar, number) in enumerate(zip(bars, numbers, strict=True)):
        is_tapped = index < tapped
        if rows:
            last = rows[-1]
            if (
                last.bar == bar
                and last.is_tapped == is_tapped
                and last.numbers[-1] + 1 == number
            ):
                rows[-1] = BarRow(last.start, bar, last.numbers + (number,), is_tapped)
                continue
        rows.append(BarRow(index, bar, (number,), is_tapped))
    return rows


def format_bar_numbers(numbers: tuple[int, ...] | list[int]) -> str:
    """Writes consecutive bar numbers as a range: "1–4", or "5" alone."""
    if len(numbers) == 1:
        return str(numbers[0])
    return f"{numbers[0]}–{numbers[-1]}"


def parse_bar_numbers(text: str, count: int) -> tuple[list[int] | None, str]:
    """
    Reads the numbers of `count` bars: a first number to count on from
    ("9"), or ranges and numbers separated by commas that name `count` bars
    ("1-8, 1-8"), where a number that doesn't follow the one before is a
    repeat or a jump.
    """
    numbers: list[int] = []
    for item in text.replace("–", "-").split(","):
        item = item.strip()
        bounds = [bound.strip() for bound in item.split("-")]
        if not 1 <= len(bounds) <= 2 or not all(
            bound.isascii() and bound.isdigit() for bound in bounds
        ):
            return None, f"'{item}' is not a bar number or a range such as 1-4."
        first, last = int(bounds[0]), int(bounds[-1])
        if last < first:
            return None, f"'{item}' counts down."
        numbers += range(first, last + 1)
        if len(numbers) > count:
            break

    if len(numbers) == 1:
        return list(range(numbers[0], numbers[0] + count)), ""
    if len(numbers) != count:
        bars = "bar" if count == 1 else "bars"
        return None, f"'{text}' numbers {len(numbers)} bars, not {count} {bars}."
    return numbers, ""


def parse_time_signature(text: str) -> tuple[PlannedBar | None, str]:
    """Reads one bar of the pattern syntax, such as "6/8" or "6/8(3 3)"."""
    result = parse(text)
    if not result.is_complete:
        return None, result.error
    if len(result.planned_bars) != 1:
        return None, "Enter one time signature, such as 3/4."
    return result.planned_bars[0], ""


def parse_taps(text: str, denominator: int) -> tuple[PlannedBar | None, str]:
    """Reads what each tap of a bar is worth, such as "3/2 3/2 1"."""
    result = parse_units("+".join(text.replace("+", " ").split()))
    if not result.is_valid:
        return None, result.error
    return PlannedBar.from_values(result.units, denominator), ""


def format_taps(bar: PlannedBar) -> str:
    return " ".join(str(value) for value in bar.values)


class BeatPatternDialog(QDialog):
    def __init__(
        self,
        initial_text: str = "",
        beat_count: int = 0,
        current_bars: list[PlannedBar] | None = None,
        numbers: list[int] | None = None,
    ) -> None:
        """
        `current_bars` are the bars the timeline has, and `numbers` their
        numbers; rows of bars that would change are highlighted.
        """
        super().__init__(
            get(Get.MAIN_WINDOW),
            Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint,
        )
        self.setWindowTitle(tilia.ui.strings.BEAT_PATTERN_DIALOG_TITLE)
        self._beat_count = beat_count
        self._current_bars = current_bars or []
        self._overrides = get_overrides(numbers or [])
        self._planned: list[PlannedBar] = []
        self._rows: list[BarRow] = []
        self._is_updating_table = False

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(5, 5, 5, 5)

        prompt = QLabel(tilia.ui.strings.BEAT_PATTERN_DIALOG_PROMPT)
        prompt.setWordWrap(True)

        self.line_edit = PatternLineEdit(initial_text)
        self.line_edit.setValidator(BeatPatternValidator(self.line_edit))
        self.line_edit.setToolTip(tilia.ui.strings.BEAT_PATTERN_DIALOG_TOOLTIP)

        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(
            tilia.ui.strings.BEAT_PATTERN_TABLE_HEADERS
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed
        )
        self.table.setMaximumHeight(MAX_TABLE_HEIGHT)
        self.table.setToolTip(tilia.ui.strings.BEAT_PATTERN_TABLE_TOOLTIP)
        self.table.itemChanged.connect(self._on_item_changed)

        self.footer = QLabel(self)
        self.footer.setTextFormat(Qt.TextFormat.PlainText)
        self.footer.setWordWrap(True)

        self.error = QLabel(self)
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        self.layout().addWidget(prompt)
        self.layout().addWidget(self.line_edit)
        self.layout().addWidget(self.table)
        self.layout().addWidget(self.footer)
        self.layout().addWidget(self.error)
        self.layout().addWidget(self.button_box)

        self.line_edit.textChanged.connect(self._on_text_changed)
        self._on_text_changed(initial_text)

    @property
    def ok_button(self) -> QPushButton:
        return self.button_box.button(QDialogButtonBox.StandardButton.Ok)

    @property
    def text(self) -> str:
        return self.line_edit.text().strip()

    @property
    def rows(self) -> list[BarRow]:
        return list(self._rows)

    def get_table_rows(self) -> list[tuple[str, str, str]]:
        return [
            tuple(
                self.table.item(row, column).text()
                for column in range(self.table.columnCount())
            )
            for row in range(self.table.rowCount())
        ]

    def get_highlighted_rows(self) -> set[int]:
        return {
            row
            for row in range(self.table.rowCount())
            if self.table.item(row, 0).background().color() == CHANGED_COLOR
        }

    def get_result(self) -> BarsEdit:
        _, tapped = lay_out(self._planned, self._beat_count)
        return BarsEdit(self.text, get_numbers(tapped, self._overrides))

    def _show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.setVisible(bool(message))

    def _on_text_changed(self, text: str) -> None:
        result = parse(text)
        self.ok_button.setEnabled(result.is_complete)
        self.table.setVisible(result.is_complete)
        self.footer.setVisible(result.is_complete)
        if not result.is_complete:
            if result.position is None or result.error.startswith("Enter"):
                self._show_error(result.error)
            else:
                self._show_error(f"{result.error} (at character {result.position + 1})")
            return

        self._show_error("")
        self._planned = result.planned_bars
        self._update_table()

    def _update_table(self) -> None:
        bars, tapped = lay_out(self._planned, self._beat_count)
        numbers = get_numbers(len(bars), self._overrides)
        self._rows = get_rows(bars, tapped, numbers)

        self._is_updating_table = True
        self.table.setRowCount(len(self._rows))
        for row_index, row in enumerate(self._rows):
            texts = [
                format_bar_numbers(row.numbers),
                format_planned_bar(row.bar),
                format_taps(row.bar),
            ]
            is_changed = self._is_changed(row)
            for column, text in enumerate(texts):
                item = QTableWidgetItem(text)
                flags = item.flags()
                if column == BARS_COLUMN and not row.is_tapped:
                    # Only measures with beats keep a number.
                    flags &= ~Qt.ItemFlag.ItemIsEditable
                item.setFlags(flags)
                if not row.is_tapped:
                    item.setForeground(QBrush(UNTAPPED_COLOR))
                if is_changed:
                    item.setBackground(CHANGED_COLOR)
                self.table.setItem(row_index, column, item)
        self._is_updating_table = False

        self.footer.setText(self._get_footer(bars, tapped))

    def _is_changed(self, row: BarRow) -> bool:
        """Whether the row's bars differ from the timeline's."""
        if not self._current_bars:
            return False
        for index in range(row.start, row.start + row.count):
            if index >= len(self._current_bars):
                return row.is_tapped
            if self._current_bars[index] != row.bar:
                return True
        return False

    def _get_footer(self, bars: list[PlannedBar], tapped: int) -> str:
        length = len(self._planned)
        lines = [
            tilia.ui.strings.BEAT_PATTERN_SUMMARY.format(
                length, "" if length == 1 else "s"
            )
        ]
        if self._beat_count:
            lines.append(
                tilia.ui.strings.BEAT_PATTERN_TAPPED.format(
                    self._beat_count,
                    "" if self._beat_count == 1 else "s",
                    tapped,
                    "" if tapped == 1 else "s",
                )
            )
        return "\n".join(lines)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._is_updating_table:
            return
        row = self._rows[item.row()]
        if item.column() == BARS_COLUMN:
            self._edit_numbers(row, item.text())
            return

        if item.column() == TIME_SIGNATURE_COLUMN:
            bar, error = parse_time_signature(item.text())
        else:
            bar, error = parse_taps(item.text(), row.bar.denominator)
        if bar is None:
            self._show_error(error)
            self._update_table()
            return

        self._show_error("")
        bars, _ = lay_out(self._planned, self._beat_count)
        for index in range(row.start, row.start + row.count):
            bars[index] = bar
        # Setting the text parses it back into the same bars and redraws the
        # table.
        self.line_edit.setText(format_planned_bars(bars))

    def _edit_numbers(self, row: BarRow, text: str) -> None:
        numbers, error = parse_bar_numbers(text, row.count)
        if numbers is None:
            self._show_error(error)
            self._update_table()
            return

        self._show_error("")
        bars, tapped = lay_out(self._planned, self._beat_count)
        all_numbers = get_numbers(tapped, self._overrides)
        all_numbers[row.start : row.start + row.count] = numbers
        # The bars after the row count on from it, unless numbered by hand.
        for index in range(row.start + row.count, tapped):
            if index not in self._overrides:
                all_numbers[index] = all_numbers[index - 1] + 1
        self._overrides = get_overrides(all_numbers)
        self._update_table()

    @classmethod
    def ask(
        cls,
        initial_text: str = "",
        beat_count: int = 0,
        current_bars: list[PlannedBar] | None = None,
        numbers: list[int] | None = None,
    ) -> tuple[bool, BarsEdit | None]:
        dialog = cls(initial_text, beat_count, current_bars, numbers)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return True, dialog.get_result()
        return False, None
