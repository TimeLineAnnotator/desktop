from typing import Sequence

from PyQt6 import QtCore
from PyQt6.QtCore import QDir
from PyQt6.QtWidgets import QFileDialog

from tilia.media import constants as media_constants
from tilia.constants import APP_NAME, FILE_EXTENSION
import tilia.ui.dialogs.basic

APP_FILE_FILTER = f"{APP_NAME} files (*.{FILE_EXTENSION})"


def ask_should_save_changes():
    return tilia.ui.dialogs.basic.ask_yes_no_or_cancel("Save changes", "Save changes to current file?")


def _get_return_from_file_dialog(dialog: QFileDialog):
    return dialog.exec(), dialog.selectedFiles()[0] if dialog.selectedFiles() else None


def ask_for_tilia_file_to_open():
    dialog = QFileDialog()
    dialog.setWindowTitle(f"Open {APP_NAME} files")
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    dialog.setFilter(QDir.Filter.Files)
    dialog.setNameFilters([APP_FILE_FILTER, "All files (*)"])
    return _get_return_from_file_dialog(dialog)


def ask_for_file_to_open(title: str, name_filters: Sequence[str]):
    dialog = QFileDialog()
    dialog.setWindowTitle(title)
    dialog.setFilter(QDir.Filter.Files)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    dialog.setNameFilters(name_filters)
    return _get_return_from_file_dialog(dialog)


def ask_for_path_to_save_tilia_file(initial_filename: str) -> tuple[str, str]:
    return QFileDialog().getSaveFileName(
        caption="Save as", directory=initial_filename, filter=APP_FILE_FILTER
    )


def ask_for_path_to_save_ogg_file(title: str, initial_name: str) -> tuple[str, str]:
    return QFileDialog().getSaveFileName(
        caption=title, directory=initial_name, filter="OGG files (*.ogg)"
    )


def ask_for_path_to_export(initial_name: str) -> tuple[str, str]:
    return QFileDialog().getSaveFileName(
        caption='Export to', directory=initial_name, filter="JSON files (*.json)"
    )


def ask_for_pdf_file():
    dialog = QFileDialog()
    dialog.setWindowTitle('Choose PDF')
    dialog.setFilter(QtCore.QDir.Filter.Files)
    dialog.setNameFilter('PDF files (*.pdf)')

    return _get_return_from_file_dialog(dialog)


def ask_retry_pdf_file():
    return tilia.ui.dialogs.basic.ask_yes_no('Invalid PDF', 'Would you like to load another PDF file?')


def ask_for_media_file():
    def get_filetypes_str(formats: list):
        filetypes = ""
        for frmt in formats:
            filetypes += "*." + frmt + " "

        return filetypes[:-2]

    audio_filetypes = get_filetypes_str(
        media_constants.SUPPORTED_AUDIO_FORMATS
        + media_constants.CONVERTIBLE_AUDIO_FORMATS
    )

    video_filetypes = get_filetypes_str(media_constants.SUPPORTED_VIDEO_FORMATS)

    all_filetypes = get_filetypes_str(
        media_constants.SUPPORTED_AUDIO_FORMATS
        + media_constants.CONVERTIBLE_AUDIO_FORMATS
        + media_constants.SUPPORTED_VIDEO_FORMATS
    )

    dialog = QFileDialog()
    dialog.setWindowTitle("Load media")
    dialog.setFilter(QtCore.QDir.Filter.Files)
    dialog.setNameFilters(
        [
            f"All supported media files ({all_filetypes})",
            f"Audio files ({audio_filetypes})",
            f"Video files ({video_filetypes})",
            "All files (*)",
        ]
    )

    return _get_return_from_file_dialog(dialog)
