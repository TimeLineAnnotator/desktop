from pathlib import Path
from typing import Sequence

from PySide6 import QtCore
from PySide6.QtCore import QDir
from PySide6.QtWidgets import QFileDialog

from tilia.media import constants as media_constants
from tilia.constants import APP_NAME, FILE_EXTENSION
import tilia.ui.dialogs.basic
from tilia.ui.dialogs.add_timeline_without_media import AddTimelineWithoutMedia

APP_FILE_FILTER = f"{APP_NAME} files (*.{FILE_EXTENSION})"


def ask_should_save_changes():
    return tilia.ui.dialogs.basic.ask_yes_no_or_cancel(
        "Save changes", "Save changes to current file?"
    )


def _get_return_from_file_dialog(dialog: QFileDialog):
    return (
        bool(dialog.exec()),
        dialog.selectedFiles()[0] if dialog.selectedFiles() else None,
    )


def ask_for_tilia_file_to_open() -> tuple[bool, str | None]:
    dialog = QFileDialog()
    dialog.setWindowTitle(f"Open {APP_NAME} files")
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    dialog.setFilter(QDir.Filter.Files)
    dialog.setNameFilters([APP_FILE_FILTER, "All files (*)"])
    return _get_return_from_file_dialog(dialog)


def ask_for_file_to_open(
    title: str, name_filters: str | Sequence[str]
) -> tuple[bool, str | None]:
    dialog = QFileDialog()
    dialog.setWindowTitle(title)
    dialog.setFilter(QDir.Filter.Files)
    dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
    if isinstance(name_filters, str):
        name_filters = [name_filters]
    dialog.setNameFilters(name_filters)
    return _get_return_from_file_dialog(dialog)


def ask_for_path_to_save(
    title: str, filter: str | list[str], initial_filename: str
) -> tuple[bool, str | None]:
    dialog = QFileDialog()
    dialog.setWindowTitle(title)
    dialog.setFileMode(QFileDialog.FileMode.AnyFile)
    dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
    if not isinstance(filter, list):
        filter = [filter]
    dialog.setNameFilters(filter)
    dialog.setDirectory(
        Path(dialog.directory().path()).resolve().__str__().replace("\\", "/")
    )
    dialog.selectFile(initial_filename)

    return _get_return_from_file_dialog(dialog)


def ask_for_path_to_save_tilia_file(initial_filename: str) -> tuple[bool, str | None]:
    return ask_for_path_to_save("Save as", APP_FILE_FILTER, initial_filename)


def ask_for_path_to_export(
    initial_name: str, file_type: str
) -> tuple[bool, str | None]:
    match file_type:
        case "json":
            filter = "JSON files (*.json)"
        case "img":
            filter = [
                "JPEG (*.jpg *.jpeg)",
                "PNG (*.png)",
                "Portable Pixmap (*.ppm)",
                "Windows Bitmap (*.bmp)",
                "X11 Bitmap (*.xbm)",
                "X11 Pixmap (*.xpm)",
            ]
        case _:
            return False, None

    return ask_for_path_to_save("Export", filter, initial_name)


def ask_for_pdf_file() -> tuple[bool, str | None]:
    dialog = QFileDialog()
    dialog.setWindowTitle("Choose PDF")
    dialog.setFilter(QtCore.QDir.Filter.Files)
    dialog.setNameFilter("PDF files (*.pdf)")

    return _get_return_from_file_dialog(dialog)


def ask_retry_media_file():
    return tilia.ui.dialogs.basic.ask_yes_or_no(
        "Invalid media path", "Would you like to load another media file?"
    )


def ask_retry_pdf_file():
    return tilia.ui.dialogs.basic.ask_yes_or_no(
        "Invalid PDF", "Would you like to load another PDF file?"
    )


def ask_for_media_file() -> tuple[bool, str | None]:
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


def ask_add_timeline_without_media() -> tuple[
    bool, AddTimelineWithoutMedia.Result | None
]:
    return AddTimelineWithoutMedia.select()
