import music21
from PyQt6.QtWidgets import (
    QDialog,
    QComboBox,
    QGridLayout,
    QLabel,
    QDialogButtonBox,
    QPushButton,
    QLineEdit,
)

from tilia import settings
from tilia.requests import post, Post
from tilia.timelines.harmony.constants import HARMONY_DISPLAY_MODES
from tilia.ui.timelines.harmony.constants import (
    NOTE_NAME_TO_INT,
    ACCIDENTAL_TO_INT,
    ROMAN_TO_INT,
    CHORD_COMMON_NAME_TO_TYPE,
)
from tilia.ui.timelines.harmony.utils import (
    QUALITY_TO_ROMAN_NUMERAL_SUFFIX,
    INT_TO_APPLIED_TO_SUFFIX,
)


class SelectHarmonyParams(QDialog):
    def __init__(self, current_key: str | None = None):
        super().__init__()
        self.setWindowTitle("Add harmony")
        layout = QGridLayout()
        self.setLayout(layout)

        step_combobox = self.step_combobox = QComboBox()
        for name, n in NOTE_NAME_TO_INT.items():
            step_combobox.addItem(name, n)

        accidental_combobox = self.accidental_combobox = QComboBox()
        for accidental, i in ACCIDENTAL_TO_INT.items():
            accidental_combobox.addItem(accidental, i)

        inversion_combobox = self.inversion_combobox = QComboBox()
        inversion_combobox.insertItem(0, "", 0)
        inversion_combobox.insertItem(1, "1st", 1)
        inversion_combobox.insertItem(2, "2nd", 2)
        inversion_combobox.insertItem(3, "3rd", 3)

        quality_combobox = self.quality_combobox = QComboBox()
        quality_combobox.setStyleSheet("combobox-popup: 0;")
        for kind in reversed(music21.harmony.CHORD_TYPES):
            quality_combobox.insertItem(0, kind.replace("-", " ").capitalize(), kind)
        quality_combobox.setCurrentIndex(0)
        quality_combobox.currentIndexChanged.connect(self.on_quality_combobox_changed)

        applied_to_combobox = self.applied_to_combobox = QComboBox()
        for i, value in INT_TO_APPLIED_TO_SUFFIX.items():
            applied_to_combobox.addItem(value, i)

        display_mode_combobox = self.display_mode_combobox = QComboBox()
        for value in HARMONY_DISPLAY_MODES:
            display_mode_combobox.addItem(value, value)
        display_mode_combobox.setCurrentText(
            settings.get("harmony_timeline", "default_harmony_display_mode")
        )

        line_edit = self.line_edit = QLineEdit()
        line_edit.textEdited.connect(self.on_text_edited)

        self.current_key = current_key
        current_key_label = QLabel(
            "Current key: None (C)"
            if not current_key
            else f"Current key: {current_key}"
        )

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(QLabel("step"), 0, 0, 1, 2)
        layout.addWidget(step_combobox, 1, 0)
        layout.addWidget(accidental_combobox, 1, 1)

        layout.addWidget(QLabel("Inversion"), 0, 2)
        layout.addWidget(inversion_combobox, 1, 2)

        layout.addWidget(QLabel("Quality"), 0, 3)
        layout.addWidget(quality_combobox, 1, 3)

        layout.addWidget(QLabel("Applied to"), 0, 4)
        layout.addWidget(applied_to_combobox, 1, 4)

        layout.addWidget(QLabel("Display as"), 0, 5)
        layout.addWidget(display_mode_combobox, 1, 5)

        layout.addWidget(line_edit, 2, 0, 1, 6)

        layout.addWidget(current_key_label, 3, 0, 1, 3)

        layout.addWidget(button_box, 3, 3, 1, 3)

        self.show()

    def result(self):
        return {
            "step": self.step_combobox.currentData(),
            "accidental": self.accidental_combobox.currentData(),
            "inversion": self.inversion_combobox.currentData(),
            "quality": self.quality_combobox.currentData(),
            "applied_to": self.applied_to_combobox.currentData(),
            "display_mode": self.display_mode_combobox.currentData(),
            "level": 1,
        }

    def on_text_edited(self):
        success = self.populate_from_text()
        if not success:
            self.line_edit.setStyleSheet("color: red")
        else:
            self.line_edit.setStyleSheet("")

    def on_quality_combobox_changed(self, *_):
        quality = self.quality_combobox.currentData()
        if quality in [
            "power",
            "pedal",
            "French",
            "German",
            "Italian",
            "Neapolitan",
            "Tristan",
        ]:
            self.inversion_combobox.setCurrentIndex(0)
            self.inversion_combobox.setEnabled(False)
        elif QUALITY_TO_ROMAN_NUMERAL_SUFFIX[quality][3] is None:
            self.inversion_combobox.setEnabled(True)
            self.inversion_combobox.removeItem(self.inversion_combobox.findData(3))
        else:
            self.inversion_combobox.setEnabled(True)
            if self.inversion_combobox.findData(3) == -1:
                self.inversion_combobox.addItem("3rd", 3)

    @staticmethod
    def _display_cant_get_harmony_params_from_text_error(text):
        post(
            Post.DISPLAY_ERROR,
            "Add harmony",
            f"Can't get harmony parameters: '{text}' is not a valid harmony",
        )

    @staticmethod
    def _format_postfix_accidental(text):
        if len(text) > 1 and text[1] == "b":
            text = text[0] + "-" + text[2:]
            if len(text) > 2 and text[2] == "b":
                text = text[:2] + "-" + text[3:]
        return text

    @staticmethod
    def _extract_prefixed_accidental(text):
        if not text:
            return "", ""

        accidental = ""

        while text and text[0] in ["-", "#", "b"]:
            accidental += text[0]
            text = text[1:]

        return text, accidental

    def _get_music21_object_from_text(self, text, key):
        text, prefixed_accidental = self._extract_prefixed_accidental(text)
        text = self._format_postfix_accidental(text)
        if text.startswith(tuple(NOTE_NAME_TO_INT)) and not prefixed_accidental:
            try:
                return music21.harmony.ChordSymbol(text), "chord"
            except ValueError:
                pass
        elif text.startswith(("I", "i", "V", "v")):
            try:
                roman_numeral = music21.roman.RomanNumeral(
                    prefixed_accidental + text, key
                )
                chord_common_name = music21.chord.Chord(
                    roman_numeral.pitches
                ).commonName
                roman_numeral.chord_type = CHORD_COMMON_NAME_TO_TYPE[chord_common_name]
                return roman_numeral, "roman"
            except (ValueError, KeyError):
                pass

        return None, None

    @staticmethod
    def _get_params_from_music21_object(obj, kind):
        step = obj.root().step
        accidental = int(obj.root().alter)
        inversion = obj.inversion()
        if kind == "roman":
            quality = obj.chord_type
            applied_to = (
                obj.secondaryRomanNumeral.figure.upper()
                if obj.secondaryRomanNumeral
                else None
            )
        else:
            quality = obj.chordKind
            applied_to = None

        return {
            "step": step,
            "accidental": accidental,
            "inversion": inversion,
            "quality": quality,
            "applied_to": applied_to,
        }

    def _populate_widgets(self, params):
        self.step_combobox.setCurrentIndex(self.step_combobox.findText(params["step"]))
        self.accidental_combobox.setCurrentIndex(
            self.accidental_combobox.findData(params["accidental"])
        )
        self.quality_combobox.setCurrentIndex(
            self.quality_combobox.findData(params["quality"])
        )
        self.inversion_combobox.setCurrentIndex(
            self.inversion_combobox.findData(params["inversion"])
        )
        if params["applied_to"]:
            self.applied_to_combobox.setCurrentIndex(
                self.applied_to_combobox.findText("/" + params["applied_to"])
            )

    def populate_from_text(self):
        text = self.line_edit.text()
        if not text:
            return False

        music21_object, object_type = self._get_music21_object_from_text(
            text, self.current_key
        )
        if not object_type:
            return False

        params = self._get_params_from_music21_object(music21_object, object_type)
        self._populate_widgets(params)
        return True
