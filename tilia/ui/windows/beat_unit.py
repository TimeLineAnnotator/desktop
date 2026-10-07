from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from PySide6.QtCore import Qt
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

import tilia.ui.strings
from tilia.requests import Get, get
from tilia.timelines.beat.units import (
    MAX_DENOMINATOR,
    fit_units,
    format_units,
    is_fit_ambiguous,
    parse_units,
)
from tilia.ui.format import format_numerator
from tilia.ui.windows.pattern_preview import PatternPreview, PreviewContent

_UNITS_CHARACTERS = set("0123456789/+")


@dataclass(frozen=True)
class BeatUnitInput:
    denominator: int
    units: str
    only_this_measure: bool


class UnitsValidator(QValidator):
    """Blocks characters that can never be part of units; see parse_units."""

    def validate(self, text: str, pos: int) -> tuple[QValidator.State, str, int]:
        if any(c not in _UNITS_CHARACTERS and not c.isspace() for c in text):
            return QValidator.State.Invalid, text, pos
        if parse_units(text).is_valid:
            return QValidator.State.Acceptable, text, pos
        return QValidator.State.Intermediate, text, pos


def get_units_preview(
    denominator: int, units_text: str, beat_count: int | None
) -> PreviewContent:
    """
    What each tap in the units pattern is worth, with a footer on how the
    pattern repeats and the time signature the measure would get.
    """
    result = parse_units(units_text)
    if not result.is_valid:
        return PreviewContent(error=result.error)

    rows = [
        (
            str(index + 1),
            format_numerator(unit),
            _describe_quarters(unit * 4 / denominator),
        )
        for index, unit in enumerate(result.units)
    ]
    if len(result.units) == 1:
        lines = ["Every tap is worth the same."]
    else:
        lines = [f"Repeats every {len(result.units)} taps, from tap 1 in each measure."]
    if beat_count is not None:
        values = fit_units(result.units, beat_count)
        numerator = format_numerator(sum(values, Fraction(0)))
        # "4 1/3/4" would be unreadable.
        separator = "/" if numerator.isdigit() else " over "
        lines.append(
            f"This measure ({beat_count} tap{'' if beat_count == 1 else 's'}) "
            f"becomes {numerator}{separator}{denominator}."
        )
        if is_fit_ambiguous(result.units, beat_count):
            lines.append(
                tilia.ui.strings.BEAT_UNIT_AMBIGUOUS_TOOLTIP.format(
                    beat_count, format_units(result.units), format_units(values)
                )
            )
    return PreviewContent(
        headers=["Tap", f"Units (1/{denominator})", "Length"],
        rows=rows,
        footer="\n".join(lines),
    )


def _describe_quarters(quarters: Fraction) -> str:
    return f"{format_numerator(quarters)} quarter" + ("s" if quarters > 1 else "")


class BeatUnitDialog(QDialog):
    def __init__(
        self,
        denominator: int,
        units: str,
        beat_count: int | None = None,
        show_scope: bool = True,
    ) -> None:
        super().__init__(
            get(Get.MAIN_WINDOW),
            Qt.WindowType.CustomizeWindowHint | Qt.WindowType.WindowTitleHint,
        )
        self.setWindowTitle(tilia.ui.strings.BEAT_UNIT_DIALOG_TITLE)
        self._beat_count = beat_count

        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(5, 5, 5, 5)

        form = QFormLayout()
        self.denominator_edit = QSpinBox()
        self.denominator_edit.setRange(1, MAX_DENOMINATOR)
        self.denominator_edit.setValue(denominator)
        self.units_edit = QLineEdit(units)
        self.units_edit.setValidator(UnitsValidator(self.units_edit))
        self.units_edit.setToolTip(tilia.ui.strings.BEAT_UNIT_UNITS_TOOLTIP)
        form.addRow(tilia.ui.strings.BEAT_UNIT_DENOMINATOR_LABEL, self.denominator_edit)
        form.addRow(tilia.ui.strings.BEAT_UNIT_UNITS_LABEL, self.units_edit)

        self.preview = PatternPreview(self)

        self.onward_option = QRadioButton(tilia.ui.strings.BEAT_UNIT_SCOPE_ONWARD)
        self.measure_option = QRadioButton(tilia.ui.strings.BEAT_UNIT_SCOPE_MEASURE)
        self._scope = QButtonGroup(self)
        self._scope.addButton(self.onward_option)
        self._scope.addButton(self.measure_option)
        self.onward_option.setChecked(True)
        self.onward_option.setVisible(show_scope)
        self.measure_option.setVisible(show_scope)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        self.layout().addLayout(form)
        self.layout().addWidget(self.preview)
        self.layout().addWidget(self.onward_option)
        self.layout().addWidget(self.measure_option)
        self.layout().addWidget(self.button_box)

        self.denominator_edit.valueChanged.connect(self._on_input_changed)
        self.units_edit.textChanged.connect(self._on_input_changed)
        self._on_input_changed()

    @property
    def ok_button(self) -> QPushButton:
        return self.button_box.button(QDialogButtonBox.StandardButton.Ok)

    @property
    def result_input(self) -> BeatUnitInput:
        return BeatUnitInput(
            self.denominator_edit.value(),
            format_units(parse_units(self.units_edit.text()).units),
            self.measure_option.isChecked(),
        )

    def _on_input_changed(self, *_) -> None:
        self.preview.set_content(
            get_units_preview(
                self.denominator_edit.value(),
                self.units_edit.text(),
                self._beat_count,
            )
        )
        self.ok_button.setEnabled(parse_units(self.units_edit.text()).is_valid)

    @classmethod
    def ask(
        cls,
        denominator: int,
        units: str,
        beat_count: int | None = None,
        show_scope: bool = True,
    ) -> tuple[bool, BeatUnitInput | None]:
        dialog = cls(denominator, units, beat_count, show_scope)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return True, dialog.result_input
        return False, None


def ask_for_beat_unit_scope() -> tuple[bool, bool]:
    """
    Asks where an edit made in the inspector applies. Returns whether the
    user answered, and whether the edit applies to this measure only.
    """
    box = QMessageBox(get(Get.MAIN_WINDOW))
    box.setWindowTitle(tilia.ui.strings.BEAT_UNIT_DIALOG_TITLE)
    box.setText(tilia.ui.strings.BEAT_UNIT_SCOPE_PROMPT)
    onward = box.addButton(
        tilia.ui.strings.BEAT_UNIT_SCOPE_ONWARD, QMessageBox.ButtonRole.AcceptRole
    )
    measure = box.addButton(
        tilia.ui.strings.BEAT_UNIT_SCOPE_MEASURE, QMessageBox.ButtonRole.AcceptRole
    )
    box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(onward)
    box.exec()
    clicked = box.clickedButton()
    if clicked not in (onward, measure):
        return False, False
    return True, clicked is measure
