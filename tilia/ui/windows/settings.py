from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QColor

from tilia.settings import settings
from tilia.requests import post, Post
from tilia.ui.windows import WindowKind
from tilia.timelines.harmony.constants import HARMONY_DISPLAY_MODES
from tilia.ui.color import get_tinted_color
from tilia.ui.consts import TINT_FACTOR_ON_SELECTION
from tilia.ui.enums import ScrollType


class SettingsWindow(QDialog):
    KIND = WindowKind.SETTINGS

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Settings")
        self.setFixedSize(400, 400)
        self.settings = {}
        self.settings_original = {}
        self.setLayout(QVBoxLayout())
        self.setup_layout()
        self.show()

        post(Post.WINDOW_OPEN_DONE, WindowKind.SETTINGS)

    def setup_layout(self):
        self._setup_widgets()
        self._setup_buttons()
        self.populate()

    def _setup_widgets(self):
        self.scroll_area = QScrollArea()
        self.scroll_area.setSizeAdjustPolicy(
            QScrollArea.SizeAdjustPolicy.AdjustToContents
        )
        self.scroll_area.setAutoFillBackground(False)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShadow(QFrame.Shadow.Sunken)
        self.scroll_area.setFrameShape(QFrame.Shape.Panel)

        content = QWidget()
        self.form_layout = QFormLayout(content)
        self.scroll_area.setWidget(content)
        self.layout().addWidget(self.scroll_area)

    def _setup_buttons(self):
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.RestoreDefaults
            | QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.button(
            QDialogButtonBox.StandardButton.RestoreDefaults
        ).clicked.connect(self.reset_fields)
        self.button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self.apply_fields
        )
        self.button_box.button(QDialogButtonBox.StandardButton.Cancel).clicked.connect(
            self.close
        )
        self.layout().addWidget(self.button_box)

    def clear_layout(self):
        self.layout().removeWidget(self.scroll_area)
        self.layout().removeWidget(self.button_box)
        self.settings.clear()

    def add_separator(self):
        line = QFrame()
        line.setFrameStyle(QFrame.Shape.HLine | QFrame.Shadow.Sunken)
        self.form_layout.addRow(line)

    def populate(self):
        def add_group(group_name):
            if group_name == "PDF_timeline":
                filled_fields.append(group_name)
                return

            self.form_layout.addRow(pretty_label(group_name), None)
            self.settings[group_name] = {}
            for name, value in self.settings_original[group_name].items():
                if group_name == "beat_timeline" and name == "default_height":
                    continue
                widget = get_widget_for_value(value)
                if (
                    "timeline" in group_name
                    and name == "default_height"
                    and widget.objectName() == "int"
                ):
                    widget.setMinimum(10)
                self.form_layout.addRow(pretty_label(name), widget)
                self.settings[group_name][name] = widget
            filled_fields.append(group_name)
            self.add_separator()

        self.settings_original = settings.get_dict()
        filled_fields = []
        add_group("general")
        for group_name in (
            group_name
            for group_name in self.settings_original.keys()
            if "timeline" in group_name
        ):
            add_group(group_name)
        for group_name in self.settings_original.keys() - set(filled_fields + ["dev"]):
            add_group(group_name)
        add_group("dev")
        self.adjustSize()

    def reset_fields(self):
        default_settings = settings.DEFAULT_SETTINGS
        current_settings = {
            group_name: {
                name: get_value_for_widget(widget) for name, widget in setting.items()
            }
            for group_name, setting in self.settings.items()
        }
        edited_settings = {}
        for group_name, setting in current_settings.items():
            for name in setting.keys():
                if (
                    current_settings[group_name][name]
                    != default_settings[group_name][name]
                ):
                    edited_settings.setdefault(group_name, {})
                    edited_settings[group_name][name] = default_settings[group_name][
                        name
                    ]
        self._save_edits(edited_settings)
        settings.reset_to_default()
        self.clear_layout()
        self.setup_layout()

    def apply_fields(self):
        self._save_edits(self._get_edits())
        self.clear_layout()
        self.setup_layout()

    def closeEvent(self, event):
        post(Post.WINDOW_CLOSE_DONE, WindowKind.SETTINGS)
        super().closeEvent(event)

    def _get_edits(self) -> dict:
        new_settings = {
            group_name: {
                name: get_value_for_widget(widget) for name, widget in setting.items()
            }
            for group_name, setting in self.settings.items()
        }
        edited_settings = {}
        for group_name, setting in new_settings.items():
            for name, value in setting.items():
                if (
                    new_settings[group_name][name]
                    != self.settings_original[group_name][name]
                ):
                    edited_settings.setdefault(group_name, {})
                    edited_settings[group_name][name] = value
        return edited_settings

    def _save_edits(self, edited_settings: dict) -> None:
        for group_name, setting in edited_settings.items():
            for name, value in setting.items():
                settings.set(group_name, name, value)

        post(Post.SETTINGS_UPDATED, [*edited_settings])


def pretty_label(input_string: str):
    return QLabel(
        " ".join(
            [
                word.title() if word.islower() else word
                for word in input_string.split("_")
            ]
        )
    )


def select_color_button(value, text=None):
    def select_color(old_color):
        new_color = QColorDialog.getColor(
            QColor(old_color),
            None,
            "Choose Color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if new_color.isValid() and new_color != old_color:
            set_color(f"#{new_color.alpha():02x}{new_color.name()[1:]}")

    def set_color(color):
        button.setStyleSheet(
            f"background-color: {color}; color: {get_tinted_color(color, TINT_FACTOR_ON_SELECTION)};"
        )

    def get_value():
        return button.styleSheet().lstrip("background-color: ").split(";")[0]

    button = QPushButton()
    button.setText(text)
    set_color(value)
    button.clicked.connect(lambda _: select_color(get_value()))
    button.setObjectName("color")
    return button


def combobox(options: list, current_value: str):
    combobox = QComboBox()
    for option in options:
        combobox.addItem(option.title(), option)
    combobox.setCurrentText(current_value.title())
    combobox.setObjectName("combobox")
    return combobox


def get_widget_for_value(value, text=None) -> QWidget:
    match value:
        case bool():
            checkbox = QCheckBox()
            checkbox.setChecked(value)
            checkbox.setObjectName("checkbox")
            return checkbox

        case int():
            int_input = QSpinBox()
            int_input.setMaximum(2147483647)
            int_input.setMinimum(1)
            int_input.setValue(value)
            int_input.setObjectName("int")
            return int_input

        case list():
            if len(value[0]) and value[0][0] == "#":
                widget = QWidget()
                widget.setObjectName("list")
                layout = QVBoxLayout(widget)
                for i in range(len(value)):
                    sub_widget = get_widget_for_value(value[i], f"Level {i + 1}")
                    layout.addWidget(sub_widget)

            else:
                widget = QTextEdit()
                widget.setText("\n".join(value))
                widget.setObjectName("text_edit")

            return widget

        case str():
            if len(value):
                if value[0] == "#":
                    return select_color_button(value, text)

                if value in HARMONY_DISPLAY_MODES:
                    return combobox(HARMONY_DISPLAY_MODES, value)

            line_edit = QLineEdit(str(value).title())
            line_edit.setObjectName("str")
            return line_edit

        case ScrollType():
            return combobox(
                ScrollType.get_option_list(), ScrollType.get_str_from_enum(value)
            )

        case _:
            raise NotImplementedError


def get_value_for_widget(widget: QWidget):
    match widget.objectName():
        case "int":
            return widget.value()

        case "text_edit":
            return [item for item in widget.toPlainText().split("\n") if item != ""]

        case "list":
            output_list = []
            for i in range(widget.layout().count()):
                output_list.append(
                    get_value_for_widget(widget.layout().itemAt(i).widget())
                )
            return output_list

        case "checkbox":
            return widget.isChecked()

        case "color":
            return widget.styleSheet().lstrip("background-color: ").split(";")[0]

        case "combobox":
            text = widget.currentText().lower()
            if text in ScrollType.get_option_list():
                return ScrollType.get_enum_from_str(text)
            return text

        case "str":
            return widget.text().lower()

        case _:
            raise NotImplementedError
