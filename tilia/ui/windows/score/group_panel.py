"""The bar above the score: what the selected notes' pitch classes are, and the
buttons that make and change note groups."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from tilia.timelines.score.pcset import PitchClassSetAnalysis
from tilia.ui import commands

NO_SELECTION_TEXT = (
    "Click notes, or drag a box around them, to see their pitch-class set."
    " Ctrl-click adds a note."
)


def format_pcs(pcs: tuple[int, ...]) -> str:
    return " ".join(str(pc) for pc in pcs)


def format_analysis(analysis: PitchClassSetAnalysis) -> str:
    """The analysis as rich text. Pitch classes are in quarter tones, with 0 on C."""
    if not analysis.pitch_classes:
        return "The selection has no pitched notes."
    forte = analysis.forte_name or "none (not a 12-note set)"
    vector = "".join(f"{count:x}" for count in analysis.interval_class_vector)
    return (
        f"<b>Prime form ({format_pcs(analysis.prime_form)})</b>"
        f" &nbsp;|&nbsp; Forte: {forte}"
        f" &nbsp;|&nbsp; Cardinality: {analysis.cardinality}"
        f" &nbsp;|&nbsp; Normal form: [{format_pcs(analysis.normal_form)}]"
        f" &nbsp;|&nbsp; Pitch classes: {{{format_pcs(analysis.pitch_classes)}}}"
        f" &nbsp;|&nbsp; Interval-class vector: &lt;{vector}&gt;"
    )


class GroupPanel(QWidget):
    def __init__(self, timeline_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.timeline_id = timeline_id
        self.group_id: str | None = None
        self.has_selection = False

        self.analysis_label = QLabel(NO_SELECTION_TEXT)
        self.analysis_label.setTextFormat(Qt.TextFormat.RichText)
        self.analysis_label.setWordWrap(True)
        self.analysis_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.analysis_label.setToolTip(
            "Pitch classes are in quarter tones, at sounding pitch, with 0 on C."
            " The interval-class vector counts classes 1 to 12, written in hexadecimal."
        )

        self.create_button = QPushButton("Group notes")
        self.create_button.setToolTip("Make a group of the selected notes (Ctrl+G)")
        self.create_button.clicked.connect(self._on_create)
        self.update_button = QPushButton("Update group")
        self.update_button.setToolTip("Give the group the selected notes")
        self.update_button.clicked.connect(self._on_update)
        self.delete_button = QPushButton("Delete group")
        self.delete_button.clicked.connect(self._on_delete)
        self.label_edit = QLineEdit()
        self.label_edit.setPlaceholderText("Group label")
        self.label_edit.setMaximumWidth(240)
        self.label_edit.editingFinished.connect(self._on_label_edited)

        # Keyboard focus stays on the score, for the app's shortcuts to keep working
        # after a click on a button or when the window is activated.
        for button in (self.create_button, self.update_button, self.delete_button):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.label_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(self.create_button)
        buttons.addWidget(self.update_button)
        buttons.addWidget(self.delete_button)
        buttons.addWidget(self.label_edit)
        buttons.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(buttons)
        layout.addWidget(self.analysis_label)
        self.show_state(None, None, "")

    def show_state(
        self,
        analysis: PitchClassSetAnalysis | None,
        group_id: str | None,
        label: str,
    ) -> None:
        """`analysis` is the selected notes', or None if no note is selected,
        and `group_id` the active group, if any."""
        self.group_id = group_id
        self.has_selection = analysis is not None
        self.analysis_label.setText(
            format_analysis(analysis) if analysis else NO_SELECTION_TEXT
        )
        self.create_button.setEnabled(self.has_selection)
        self.update_button.setEnabled(self.has_selection and group_id is not None)
        self.delete_button.setEnabled(group_id is not None)
        self.label_edit.setEnabled(group_id is not None)
        if self.label_edit.text() != label:
            self.label_edit.setText(label)

    def _on_create(self) -> None:
        commands.execute("timeline.score.group.create", timeline_id=self.timeline_id)

    def _on_update(self) -> None:
        commands.execute(
            "timeline.score.group.set_notes",
            group_id=self.group_id,
            timeline_id=self.timeline_id,
        )

    def _on_delete(self) -> None:
        commands.execute(
            "timeline.score.group.delete",
            group_id=self.group_id,
            timeline_id=self.timeline_id,
        )

    def _on_label_edited(self) -> None:
        if self.group_id is not None:
            commands.execute(
                "timeline.score.group.set_label",
                self.label_edit.text(),
                group_id=self.group_id,
                timeline_id=self.timeline_id,
            )
