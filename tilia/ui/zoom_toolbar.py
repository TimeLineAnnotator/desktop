from __future__ import annotations

import math

from PySide6.QtCore import Qt
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

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.addWidget(spacer)

        self.addAction(commands.get_qaction("view.zoom.out"))

        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(0, _SLIDER_STEPS)
        self._slider.setFixedWidth(100)
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
        self._edit.valueChanged.connect(self._on_edit_committed)
        self.addWidget(self._edit)

        listen(self, Post.ZOOM_TOOLBAR_UPDATE, self._on_zoom_toolbar_update)

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
