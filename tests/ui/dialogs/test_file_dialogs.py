from unittest.mock import patch

import pytest
from PySide6.QtCore import QDir
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

DIALOG_BUILDERS = OPEN_DIALOG_BUILDERS | {
    "save": lambda: file_dialogs.ask_for_path_to_save(
        "Save as", "TiLiA files (*.tla)", "file.tla"
    ),
}


def build_dialog(builder):
    """Runs a dialog-creating function, returning the dialog instead of executing it."""
    with patch.object(
        file_dialogs, "_get_return_from_file_dialog", return_value=(False, None)
    ) as get_return:
        builder()

    return get_return.call_args.args[0]


DEFAULT_FILTER = (
    QDir.Filter.Dirs
    | QDir.Filter.Files
    | QDir.Filter.Drives
    | QDir.Filter.AllDirs
    | QDir.Filter.NoDot
    | QDir.Filter.NoDotDot
)


class TestDirectoriesAreListed:
    @pytest.mark.parametrize("name", DIALOG_BUILDERS)
    def test_dialog_keeps_default_filter(self, name, qtui):
        # QFileDialog.setFilter replaces Qt's default filter instead of adding
        # to it, so no dialog may call it. Dropping AllDirs hides every folder
        # and leaves the user unable to navigate; dropping NoDot/NoDotDot lists
        # "." and ".." as entries. Which of the two you get depends on call
        # order, because setFileMode() re-derives the filter and puts AllDirs
        # and Drives back. See issue #565.
        dialog = build_dialog(DIALOG_BUILDERS[name])

        assert dialog.filter() == DEFAULT_FILTER


class TestOpenDialogsRequireExistingFile:
    @pytest.mark.parametrize("name", OPEN_DIALOG_BUILDERS)
    def test_open_dialog_only_accepts_existing_file(self, name, qtui):
        # QFileDialog defaults to FileMode.AnyFile, which accepts a filename the
        # user typed that does not exist on disk. Every dialog that opens an
        # existing file must opt into FileMode.ExistingFile, or
        # _get_return_from_file_dialog hands the caller a bogus path as success.
        dialog = build_dialog(OPEN_DIALOG_BUILDERS[name])

        assert dialog.fileMode() == QFileDialog.FileMode.ExistingFile
