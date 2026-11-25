"""The Metadata window's box of names, opened with "Edit fields...". What it changes
is in `test_media_metadata_window.py`."""

from unittest.mock import patch

from PySide6.QtWidgets import QLabel, QPushButton

from tilia.ui import commands
from tilia.ui.windows import WindowKind
from tilia.ui.windows.metadata_edit_fields import EditMetadataFieldsDialog


def test_it_says_one_name_per_line_above_the_names(qtui):
    # TimeLineAnnotator/project-management#692, point 3, b.
    commands.execute("window.open.metadata")
    window = qtui._windows[WindowKind.MEDIA_METADATA]
    opened = []

    def exec_(dialog):
        opened.append(dialog)

    with patch.object(EditMetadataFieldsDialog, "exec", new=exec_):
        next(
            button
            for button in window.findChildren(QPushButton)
            if button.text() == "Edit fields..."
        ).click()

    (dialog,) = opened
    (words,) = dialog.findChildren(QLabel)
    assert words.text() == "One name per line."
    layout = dialog.layout()
    assert layout.indexOf(words) < layout.indexOf(dialog.text_edit)
    window.close()
