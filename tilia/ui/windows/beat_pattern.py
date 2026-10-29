"""
The dialog where a beat timeline's bars are written: a pattern of time
signatures on one line (see `tilia.timelines.beat.pattern`), and a table of
the bars, where each row's bar numbers, time signature and taps can be
edited.

The table lists the bars the tapped beats make, as they are, then the bars
the pattern plans after them. Editing the pattern lays it over every beat
again. Editing a row of tapped bars changes those bars only; the pattern,
which bars tapped later follow, stays as it is. Editing a row of bars not
tapped yet changes the pattern.
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
    format_planned_bars,
    parse,
    parse_time_signature,
    parse_time_signature_over_taps,
)
from tilia.timelines.beat.units import parse_units
from tilia.ui.timelines.beat_bars import BarRow, format_row, get_rows

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
    """
    What the dialog was left with: the pattern, and the bars the tapped
    beats fill, with their numbers.
    """

    pattern: str
    bars: list[PlannedBar]
    numbers: list[int]


def lay_out(
    bars: list[PlannedBar], plan: list[PlannedBar], beat_count: int
) -> tuple[list[PlannedBar], int]:
    """
    The bars `beat_count` beats make: `bars` in order while there are beats
    for them, then bars of `plan`, going on from the bar after the last and
    starting it again from its first as often as the beats need; then the
    rest of `plan`. Also returns how many of them the beats reach.
    """
    laid: list[PlannedBar] = []
    beats = 0
    for bar in bars:
        if beats >= beat_count:
            break
        laid.append(bar)
        beats += bar.beat_count
    while beats < beat_count:
        bar = plan[len(laid) % len(plan)]
        laid.append(bar)
        beats += bar.beat_count
    tapped = len(laid)
    return laid + plan[tapped:], tapped


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


def parse_bar_numbers(text: str, count: int) -> tuple[list[int] | None, str]:
    """
    Reads the numbers of `count` bars: a first number to count on from
    ("9"), or ranges and numbers separated by commas that name `count` bars
    ("1-8, 1-8"), where a number that doesn't follow the one before is a
    repeat or a jump.
    """
    numbers: list[int] = []
    total = 0
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
        total += last - first + 1
        # Counted rather than listed past the row's bars, as a range may be
        # huge.
        if total <= count:
            numbers += range(first, last + 1)

    if total == 1:
        return list(range(numbers[0], numbers[0] + count)), ""
    if total != count:
        bars = "bar" if count == 1 else "bars"
        return None, f"'{text}' numbers {total} bars, not {count} {bars}."
    return numbers, ""


def parse_taps(text: str, denominator: int) -> tuple[PlannedBar | None, str]:
    """Reads what each tap of a bar is worth, such as "3/2 3/2 1"."""
    result = parse_units("+".join(text.replace("+", " ").split()))
    if not result.is_valid:
        return None, result.error
    return PlannedBar.from_values(result.units, denominator), ""


class BeatPatternDialog(QDialog):
    def __init__(
        self,
        initial_text: str = "",
        beat_count: int = 0,
        current_bars: list[PlannedBar] | None = None,
        numbers: list[int] | None = None,
        focus_bar: int | None = None,
    ) -> None:
        """
        `current_bars` are the bars the timeline has, and `numbers` their
        numbers; rows of bars that would change are highlighted. The table
        starts scrolled to the row of `focus_bar`.
        """
        super().__init__(
            get(Get.MAIN_WINDOW),
            Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint,
        )
        self.setWindowTitle(tilia.ui.strings.BEAT_PATTERN_DIALOG_TITLE)
        self._beat_count = beat_count
        self._current_bars = current_bars or []
        self._overrides = get_overrides(numbers or [])
        self._plan: list[PlannedBar] = []
        # The tapped bars, where they don't simply follow the pattern.
        self._bars: list[PlannedBar] = []
        # Set while a row edit rewrites the pattern, which then keeps the
        # tapped bars rather than laying the pattern over them.
        self._is_writing_plan = False
        self._rows: list[BarRow] = []
        # The bar the dialog was opened at has a row of its own, so it can
        # be edited apart from the alike bars around it.
        self._row_breaks = (
            frozenset() if focus_bar is None else frozenset({focus_bar, focus_bar + 1})
        )
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
        if self._current_bars and parse(initial_text).is_complete:
            self._bars = list(self._current_bars)
            self._update_table()
        if focus_bar is not None:
            self.focus_bar(focus_bar)

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

    def focus_bar(self, bar_index: int) -> None:
        """Scrolls to the row of a bar and makes it the current one."""
        for row_index, row in enumerate(self._rows):
            if row.start <= bar_index < row.start + row.count:
                self.table.setCurrentCell(row_index, TIME_SIGNATURE_COLUMN)
                self.table.scrollToItem(
                    self.table.item(row_index, TIME_SIGNATURE_COLUMN)
                )
                return

    @property
    def current_row(self) -> int:
        return self.table.currentRow()

    def _lay_out(self) -> tuple[list[PlannedBar], int]:
        return lay_out(self._bars, self._plan, self._beat_count)

    def get_result(self) -> BarsEdit:
        bars, tapped = self._lay_out()
        return BarsEdit(self.text, bars[:tapped], get_numbers(tapped, self._overrides))

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
        self._plan = result.planned_bars
        if not self._is_writing_plan:
            self._bars = []
        self._update_table()

    def _update_table(self) -> None:
        bars, tapped = self._lay_out()
        numbers = get_numbers(len(bars), self._overrides)
        self._rows = get_rows(bars, tapped, numbers, self._row_breaks)

        self._is_updating_table = True
        self.table.setRowCount(len(self._rows))
        for row_index, row in enumerate(self._rows):
            is_changed = self._is_changed(row)
            for column, text in enumerate(format_row(row)):
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
        length = len(self._plan)
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

        if item.column() == TIME_SIGNATURE_COLUMN and row.is_tapped:
            # A tapped bar keeps its taps, unless the text gives others.
            bar, error = parse_time_signature_over_taps(item.text(), row.bar.beat_count)
        elif item.column() == TIME_SIGNATURE_COLUMN:
            bar, error = parse_time_signature(item.text())
        else:
            bar, error = parse_taps(item.text(), row.bar.denominator)
        if bar is None:
            self._show_error(error)
            self._update_table()
            return

        self._show_error("")
        if row.is_tapped:
            bars, tapped = self._lay_out()
            bars = bars[:tapped]
            for index in range(row.start, row.start + row.count):
                bars[index] = bar
            self._bars = bars
            self._update_table()
            return

        # Bars not tapped yet are the pattern's, by position.
        plan = list(self._plan)
        for index in range(row.start, row.start + row.count):
            plan[index] = bar
        self._is_writing_plan = True
        try:
            # Setting the text parses it back into the same bars and redraws
            # the table.
            self.line_edit.setText(format_planned_bars(plan))
        finally:
            self._is_writing_plan = False

    def _edit_numbers(self, row: BarRow, text: str) -> None:
        numbers, error = parse_bar_numbers(text, row.count)
        if numbers is None:
            self._show_error(error)
            self._update_table()
            return

        self._show_error("")
        _, tapped = self._lay_out()
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
        focus_bar: int | None = None,
    ) -> tuple[bool, BarsEdit | None]:
        dialog = cls(initial_text, beat_count, current_bars, numbers, focus_bar)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return True, dialog.get_result()
        return False, None
