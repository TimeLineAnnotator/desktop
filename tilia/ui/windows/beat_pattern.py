from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QValidator
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

import tilia.ui.strings
from tilia.requests import Get, get
from tilia.timelines.beat.pattern import BarRun, ParseResult, group_runs, parse
from tilia.ui.windows.pattern_preview import PatternPreview, PreviewContent

_PATTERN_CHARACTERS = set("0123456789[]")


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


def _describe_bars(run: BarRun) -> str:
    if run.count == 1:
        return str(run.start + 1)
    return f"{run.start + 1}–{run.start + run.count}"


def _describe_bar_numbers(bars: list[int]) -> str:
    numbers = ", ".join(str(bar + 1) for bar in bars)
    return ("Bar " if len(bars) == 1 else "Bars ") + numbers


def get_pattern_preview(
    result: ParseResult,
    beat_count: int | None = None,
    overwritten_bars: list[int] | None = None,
) -> PreviewContent:
    """
    The bars a pattern expands to, grouped where consecutive bars are equal.
    `overwritten_bars` are 0-based indices of the timeline's bars set by hand
    that applying the pattern would change; their rows are highlighted.
    """
    if not result.is_complete:
        if result.position is None or result.error.startswith("Enter"):
            return PreviewContent(error=result.error)
        return PreviewContent(
            error=f"{result.error} (at character {result.position + 1})"
        )

    runs = group_runs(result.bars)
    pattern_length = len(result.bars)
    overwritten_in_pattern = {bar % pattern_length for bar in overwritten_bars or []}
    highlighted = frozenset(
        index
        for index, run in enumerate(runs)
        if any(
            run.start <= bar < run.start + run.count for bar in overwritten_in_pattern
        )
    )

    total_beats = sum(result.bars)
    lines = [
        f"{pattern_length} bar{'' if pattern_length == 1 else 's'}, "
        f"{total_beats} beat{'' if total_beats == 1 else 's'}, "
        "then the pattern repeats from bar 1."
    ]
    if beat_count is not None:
        lines.append(f"{beat_count} beat{'' if beat_count == 1 else 's'} tapped.")
    if overwritten_bars:
        lines.append(
            f"{_describe_bar_numbers(overwritten_bars)} "
            f"{'was' if len(overwritten_bars) == 1 else 'were'} "
            "set by hand and will be overwritten."
        )

    return PreviewContent(
        headers=["Bars", "Beats per bar"],
        rows=[(_describe_bars(run), str(run.beats)) for run in runs],
        footer="\n".join(lines),
        highlighted_rows=highlighted,
    )


class BeatPatternDialog(QDialog):
    def __init__(
        self,
        initial_text: str = "",
        beat_count: int | None = None,
        get_overwritten_bars: Callable[[list[int]], list[int]] | None = None,
    ):
        super().__init__(
            get(Get.MAIN_WINDOW),
            Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint,
        )
        self.setWindowTitle(tilia.ui.strings.BEAT_PATTERN_DIALOG_TITLE)
        self._beat_count = beat_count
        self._get_overwritten_bars = get_overwritten_bars

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(5, 5, 5, 5)

        prompt = QLabel(tilia.ui.strings.BEAT_PATTERN_DIALOG_PROMPT)

        self.line_edit = PatternLineEdit(initial_text)
        self.line_edit.setValidator(BeatPatternValidator(self.line_edit))
        self.line_edit.setToolTip(tilia.ui.strings.BEAT_PATTERN_DIALOG_TOOLTIP)

        self.preview = PatternPreview(self)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        self.layout().addWidget(prompt)
        self.layout().addWidget(self.line_edit)
        self.layout().addWidget(self.preview)
        self.layout().addWidget(self.button_box)

        self.line_edit.textChanged.connect(self._on_text_changed)
        self._on_text_changed(initial_text)

    @property
    def ok_button(self):
        return self.button_box.button(QDialogButtonBox.StandardButton.Ok)

    @property
    def text(self) -> str:
        return self.line_edit.text().strip()

    def _on_text_changed(self, text: str) -> None:
        result = parse(text)
        overwritten = (
            self._get_overwritten_bars(result.bars)
            if result.is_complete and self._get_overwritten_bars
            else []
        )
        self.preview.set_content(
            get_pattern_preview(result, self._beat_count, overwritten)
        )
        self.ok_button.setEnabled(result.is_complete)

    @classmethod
    def ask(
        cls,
        initial_text: str = "",
        beat_count: int | None = None,
        get_overwritten_bars: Callable[[list[int]], list[int]] | None = None,
    ) -> tuple[bool, str]:
        dialog = cls(initial_text, beat_count, get_overwritten_bars)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return True, dialog.text
        return False, ""
