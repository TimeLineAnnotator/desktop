from __future__ import annotations

import functools
from enum import Enum, auto

from typing import Any, Callable, cast

from PySide6.QtWidgets import (
    QDockWidget,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QWidget,
    QSizePolicy,
    QSpinBox,
    QComboBox,
    QStackedWidget,
    QFrame,
)

from PySide6.QtCore import Qt, QKeyCombination

from tilia.requests import Post, listen, stop_listening_to_all, post, Get, get
from tilia.utils import get_tilia_class_string
from tilia.timelines.base.component import TimelineComponent
from tilia.ui.windows.kinds import WindowKind

PADX = 5
PADY = 5

HIDE_FIELD = "__INSPECT_HIDEFIELD"


class InspectRowKind(Enum):
    SPIN_BOX = auto()
    COMBO_BOX = auto()
    SINGLE_LINE_EDIT = auto()
    MULTI_LINE_EDIT = auto()
    LABEL = auto()
    SEPARATOR = auto()


RowInfo = tuple[str, InspectRowKind, Callable[[], Any | None]]


class Inspect(QDockWidget):
    KIND = WindowKind.INSPECT

    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        self.setObjectName("inspector")
        self.setWindowTitle("Inspector")
        self.setMinimumWidth(250)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.setFloating(False)
        self._setup_requests()
        self.inspected_objects_stack = []
        self.element_id = ""
        self.currently_inspected_class = None
        self.field_name_to_widgets = None

        self.stack_widget = QStackedWidget(self)
        self.setWidget(self.stack_widget)

        self.inspect_widget = QWidget(self.stack_widget)
        self.inspect_layout = QFormLayout(self.inspect_widget)
        self.inspect_widget.setLayout(self.inspect_layout)

        self.empty_label = QLabel("<h2> No element selected.</h2>")
        self.empty_label.setStyleSheet("color:grey;padding:10px")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )

        self.stack_widget.addWidget(self.inspect_widget)
        self.stack_widget.addWidget(self.empty_label)

        post(Post.WINDOW_OPEN_DONE, WindowKind.INSPECT)

    def __str__(self):
        return get_tilia_class_string(self)

    def _setup_requests(self):
        LISTENS = {
            (Post.INSPECTABLE_ELEMENT_SELECTED, self.on_element_selected),
            (Post.INSPECTABLE_ELEMENT_DESELECTED, self.on_element_deselected),
            (Post.TIMELINE_COMPONENT_SET_DATA_DONE, self.on_component_set_data_done),
        }

        for post_, callback in LISTENS:
            listen(self, post_, callback)

    def keyPressEvent(self, a0):
        if a0.keyCombination() not in {
            QKeyCombination(Qt.KeyboardModifier.NoModifier, Qt.Key.Key_Enter),
            QKeyCombination(Qt.KeyboardModifier.NoModifier, Qt.Key.Key_Return),
            QKeyCombination(Qt.KeyboardModifier.NoModifier, Qt.Key.Key_Escape),
        }:
            return super().keyPressEvent(a0)
        self.close()

    def closeEvent(self, event, **kwargs):
        stop_listening_to_all(self)
        post(Post.WINDOW_CLOSE_DONE, WindowKind.INSPECT)
        super().closeEvent(event)

    def display_not_selected_frame(self):
        raise NotImplementedError

    def on_component_set_data_done(self, timeline_id, element_id, *__):
        ids_in_inspected_stack = [id for *_, id in self.inspected_objects_stack]
        if element_id not in ids_in_inspected_stack:
            return

        element = get(Get.TIMELINE_UI_ELEMENT, timeline_id, element_id)
        if not hasattr(element, "get_inspector_dict"):
            return

        self.update_values(element.get_inspector_dict(), element_id)

    def _select_first_row(self):
        if isinstance(self.focusProxy(), (QLineEdit, QTextEdit)):
            proxy = cast(QLineEdit | QTextEdit, self.focusProxy())
            proxy.selectAll()

    def setFocus(self):
        super().setFocus()
        self._select_first_row()

    def on_element_selected(
        self,
        element_class: type[TimelineComponent],
        inspector_fields: RowInfo,
        inspector_values: dict[str, str],
        element_id: int,
    ):
        self.setUpdatesEnabled(False)
        self.update_rows(element_class, inspector_fields)
        self.update_values(inspector_values, element_id)
        self.update_inspected_object_stack(
            element_class, inspector_fields, inspector_values, element_id
        )

        if self.hasFocus():
            self._select_first_row()

        self.setWindowTitle(f"Inspector - {element_class.__name__}")
        self.stack_widget.setCurrentWidget(self.inspect_widget)
        self.setUpdatesEnabled(True)
        self.raise_()

    def update_inspected_object_stack(self, cls, field, values, id):
        if (cls, field, values, id) not in self.inspected_objects_stack:
            self.inspected_objects_stack.append((cls, field, values, id))

    def update_rows(
        self,
        element_class: type[TimelineComponent],
        inspector_fields: RowInfo,
    ):
        if element_class != self.currently_inspected_class:
            self.clear_layout()
            self.add_rows(inspector_fields)
            self.currently_inspected_class = element_class

    def clear_layout(self):
        self.stack_widget.removeWidget(self.inspect_widget)
        self.inspect_widget = QWidget(self.stack_widget)
        self.inspect_layout = QFormLayout(self.inspect_widget)
        self.inspect_widget.setLayout(self.inspect_layout)
        self.stack_widget.addWidget(self.inspect_widget)

    def on_element_deselected(self, element_id: int):
        try:
            element_index = [
                self.inspected_objects_stack.index(obj)
                for obj in self.inspected_objects_stack
                if obj[-1] == element_id
            ][0]
        except IndexError:
            return

        self.setUpdatesEnabled(False)
        self.inspected_objects_stack.pop(element_index)

        if self.inspected_objects_stack:
            (
                element_class,
                inspector_fields,
                inspector_values,
                element_id,
            ) = self.inspected_objects_stack[-1]

            self.update_rows(element_class, inspector_fields)
            self.update_values(inspector_values, element_id)
        else:
            self.clear_widgets()
            for _, (left_widget, right_widget) in self.field_name_to_widgets.items():
                left_widget.hide()
                right_widget.setEnabled(False)
                right_widget.hide()

            self.setWindowTitle("Inspector")
            self.stack_widget.setCurrentWidget(self.empty_label)

        self.setUpdatesEnabled(True)

    def update_values(self, field_values: dict[str, str], element_id: int):
        self.element_id = element_id
        for field_name, value in field_values.items():
            widget = self.field_name_to_widgets[field_name][1]

            self.update_value(widget, value)
            self.hide_or_show_field(field_name, value)

    def update_value(self, widget: QLineEdit | QLabel | QTextEdit, value: Any):
        widget.setEnabled(True)
        self.set_widget_value(widget, value)

    @staticmethod
    def set_widget_value(widget, value):
        if isinstance(widget, (QLineEdit, QLabel)):
            if widget.text() != value:
                widget.setText(value)
        elif isinstance(widget, QTextEdit):
            if widget.toPlainText() != value:
                widget.setText(value)
        elif isinstance(widget, QComboBox):
            widget.setCurrentIndex(widget.findData(value))
        elif isinstance(widget, QSpinBox):
            widget.setValue(value)

    def hide_or_show_field(self, field_name, value):
        if value == HIDE_FIELD:
            self.field_name_to_widgets[field_name][0].hide()
            self.field_name_to_widgets[field_name][1].hide()
        else:
            self.field_name_to_widgets[field_name][0].show()
            self.field_name_to_widgets[field_name][1].show()

    def clear_widgets(self):
        for _, widget in self.field_name_to_widgets.values():
            if isinstance(widget, (QLineEdit, QLabel, QTextEdit)):
                widget.setText("")
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
            elif isinstance(widget, QSpinBox):
                widget.setValue(widget.minimum())

    def delete_all_rows(self):
        for _ in range(self.inspect_layout.rowCount()):
            self.inspect_layout.removeRow(0)

    def on_line_edit_changed(self, field_name, value):
        post(Post.INSPECTOR_FIELD_EDITED, field_name, value, self.element_id, id(self))

    def on_text_edit_changed(self, field_name, text_edit):
        post(
            Post.INSPECTOR_FIELD_EDITED,
            field_name,
            text_edit.toPlainText(),
            self.element_id,
            id(self),
        )

    def on_spin_box_changed(self, field_name, spin_box):
        post(
            Post.INSPECTOR_FIELD_EDITED,
            field_name,
            spin_box.value(),
            self.element_id,
            id(self),
        )

    def on_combo_box_changed(self, field_name, combo_box):
        post(
            Post.INSPECTOR_FIELD_EDITED,
            field_name,
            combo_box.currentData(),
            self.element_id,
            id(self),
        )

    def _get_widget_for_row(self, kind: InspectRowKind, name: str, kwargs):
        match kind:
            case InspectRowKind.LABEL:
                widget = QLabel(self.inspect_widget)
            case InspectRowKind.SINGLE_LINE_EDIT:
                widget = QLineEdit(self.inspect_widget)
                widget.textChanged.connect(
                    functools.partial(self.on_line_edit_changed, name)
                )
            case InspectRowKind.MULTI_LINE_EDIT:
                widget = QTextEdit(self.inspect_widget)
                widget.setAcceptRichText(False)
                widget.textChanged.connect(
                    functools.partial(self.on_text_edit_changed, name, widget)
                )
            case InspectRowKind.SEPARATOR:
                widget = QFrame()
                widget.setFrameStyle(QFrame.Shape.HLine | QFrame.Shadow.Sunken)
            case InspectRowKind.SPIN_BOX:
                widget = QSpinBox()
                widget.setMinimum(kwargs["min"])
                widget.setMaximum(kwargs["max"])
                widget.valueChanged.connect(
                    functools.partial(self.on_spin_box_changed, name, widget)
                )
            case InspectRowKind.COMBO_BOX:
                widget = QComboBox()
                for value, data in kwargs["items"]:
                    widget.addItem(str(value), data)
                widget.currentIndexChanged.connect(
                    functools.partial(self.on_combo_box_changed, name, widget)
                )
            case _:
                widget = None

        return widget

    def add_rows(
        self, field_params: tuple[str, InspectRowKind, Callable[[], Any | None]]
    ):
        self.field_name_to_widgets = {}

        for name, kind, get_kwargs in field_params:
            left_widget = QLabel(name, self.inspect_widget)
            right_widget = self._get_widget_for_row(
                kind, name, get_kwargs() if get_kwargs else None
            )

            right_widget.setSizePolicy(
                QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Maximum
            )
            right_widget.setMaximumHeight(50)
            self.inspect_layout.addRow(left_widget, right_widget)

            self.field_name_to_widgets[name] = (left_widget, right_widget)

        self.setFocusProxy(self.inspect_layout.itemAt(1).widget())
