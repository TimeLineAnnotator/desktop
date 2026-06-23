from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QSizePolicy,
    QSlider,
    QToolBar,
    QWidget,
)

from tilia.requests import Get, Post, get, listen
from tilia.ui import commands

_MIN = 0.01
_MAX = 10.0
_SLIDER_STEPS = 200

_LOG_MIN = math.log(_MIN)
_LOG_RANGE = math.log(_MAX) - _LOG_MIN


def _ratio_to_slider(ratio: float) -> int:
    return round((math.log(max(ratio, _MIN)) - _LOG_MIN) / _LOG_RANGE * _SLIDER_STEPS)


def _slider_to_ratio(value: int) -> float:
    return math.exp(_LOG_MIN + _LOG_RANGE * value / _SLIDER_STEPS)


class ZoomToolbar(QToolBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Zoom toolbar")
        self.setMovable(False)
        self.setFloatable(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.setMaximumHeight(30)
        self.setIconSize(QSize(16, 16))

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.addWidget(spacer)

        self.addAction(commands.get_qaction("view.zoom.out"))

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, _SLIDER_STEPS)
        self._slider.setFixedWidth(100)
        # Shrink the handle/groove to match the 16px toolbar icons; the native
        # handle otherwise dwarfs them. palette() keeps it theme-aware.
        self._apply_slider_stylesheet()
        self._slider.setValue(_ratio_to_slider(1.0))
        self._slider.sliderMoved.connect(self._on_slider_moved)
        self._slider.sliderReleased.connect(self._on_slider_released)
        self.addWidget(self._slider)

        self.addAction(commands.get_qaction("view.zoom.in"))

        self._edit = QDoubleSpinBox(
            suffix="%",
            decimals=1,
            value=100,
            stepType=QDoubleSpinBox.StepType.AdaptiveDecimalStepType,
        )
        self._edit.setFrame(False)
        self._edit.setRange(0, math.inf)
        self._edit.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self._edit.setFixedWidth(60)
        # Commit only on Enter/focus-out instead of on every keystroke, so
        # typing "250" doesn't fire a full re-zoom at 2%, 25%, then 250%.
        self._edit.setKeyboardTracking(False)
        self._edit.valueChanged.connect(self._on_edit_committed)
        self.addWidget(self._edit)

        listen(self, Post.ZOOM_TOOLBAR_UPDATE, self._on_zoom_toolbar_update)

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.PaletteChange:
            self._apply_slider_stylesheet()
        super().changeEvent(event)

    def _apply_slider_stylesheet(self) -> None:
        self._slider.setStyleSheet(
            "QSlider::groove:horizontal{height:4px;border-radius:2px;"
            "background:palette(window-text);}"
            "QSlider::handle:horizontal{width:12px;height:12px;margin:-4px 0;"
            "border-radius:6px;background:palette(button);"
            "border:1px solid palette(button-text);}"
        )

    def _update_ui(self, ratio: float) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(_ratio_to_slider(ratio))
        self._slider.blockSignals(False)
        self._edit.blockSignals(True)
        self._edit.setValue(ratio * 100)
        self._edit.blockSignals(False)

    def _commit_zoom(self, ratio: float) -> None:
        if not commands.execute("view.zoom.set", ratio):
            self._update_ui(get(Get.CURRENT_ZOOM))

    def _on_slider_moved(self, value: int) -> None:
        self._edit.blockSignals(True)
        self._edit.setValue(_slider_to_ratio(value) * 100)
        self._edit.blockSignals(False)

    def _on_slider_released(self) -> None:
        self._commit_zoom(_slider_to_ratio(self._slider.value()))

    def _on_edit_committed(self, pct: float) -> None:
        self._commit_zoom(pct / 100)

    def _on_zoom_toolbar_update(self, ratio: float) -> None:
        self._update_ui(ratio)
