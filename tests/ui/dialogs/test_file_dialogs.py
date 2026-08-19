from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QFileDialog

from tilia.ui.dialogs import file as file_dialogs

OPEN_DIALOG_BUILDERS = {
    "open tilia file": lambda: file_dialogs.ask_for_tilia_file_to_open(),
    "open file": lambda: file_dialogs.ask_for_file_to_open(
        "Import", "CSV files (*.csv)"
    ),
    "pdf": lambda: file_dialogs.ask_for_pdf_file(),
    "media": lambda: file_dialogs.ask_for_media_file(),
}


def build_dialog(builder):
    """Runs a dialog-creating function, returning the dialog instead of executing it."""
    captured = []

    def capture(dialog):
        captured.append(dialog)
        return False, None

    with patch.object(file_dialogs, "_get_return_from_file_dialog", capture):
        builder()

    return captured[0]


class TestOpenDialogsRequireExistingFile:
    @pytest.mark.parametrize("name", OPEN_DIALOG_BUILDERS)
    def test_open_dialog_only_accepts_existing_file(self, name, qtui):
        # QFileDialog defaults to FileMode.AnyFile, which accepts a filename the
        # user typed that does not exist on disk. Every dialog that opens an
        # existing file must opt into FileMode.ExistingFile, or
        # _get_return_from_file_dialog hands the caller a bogus path as success.
        dialog = build_dialog(OPEN_DIALOG_BUILDERS[name])

        assert dialog.fileMode() == QFileDialog.FileMode.ExistingFile
