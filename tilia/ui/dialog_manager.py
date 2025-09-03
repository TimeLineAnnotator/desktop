from tilia.requests import serve, Get

from tilia.ui.dialogs.file import (
    ask_should_save_changes,
    ask_for_file_to_open,
    ask_for_path_to_save_tilia_file,
    ask_for_tilia_file_to_open,
    ask_for_media_file,
    ask_for_path_to_save,
    ask_for_pdf_file,
    ask_retry_media_file,
    ask_retry_pdf_file,
    ask_for_path_to_export,
    ask_add_timeline_without_media,
)
from tilia.ui.dialogs.basic import (
    ask_for_string,
    ask_for_float,
    ask_for_int,
    ask_for_color,
    ask_yes_or_no,
)
from tilia.ui.dialogs.harmony_params import ask_for_harmony_params
from tilia.ui.dialogs.mode_params import ask_for_mode_params
from tilia.ui.timelines.beat.dialogs import (
    ask_for_beat_pattern,
    ask_beat_timeline_fill_method,
)


class DialogManager:
    def __init__(self):
        SERVES = {
            (Get.FROM_USER_SHOULD_SAVE_CHANGES, ask_should_save_changes),
            (Get.FROM_USER_SAVE_PATH_TILIA, ask_for_path_to_save_tilia_file),
            (Get.FROM_USER_SAVE_PATH, ask_for_path_to_save),
            (Get.FROM_USER_EXPORT_PATH, ask_for_path_to_export),
            (Get.FROM_USER_TILIA_FILE_PATH, ask_for_tilia_file_to_open),
            (Get.FROM_USER_FILE_PATH, ask_for_file_to_open),
            (Get.FROM_USER_STRING, ask_for_string),
            (Get.FROM_USER_FLOAT, ask_for_float),
            (Get.FROM_USER_INT, ask_for_int),
            (Get.FROM_USER_YES_OR_NO, ask_yes_or_no),
            (Get.FROM_USER_COLOR, ask_for_color),
            (Get.FROM_USER_BEAT_PATTERN, ask_for_beat_pattern),
            (Get.FROM_USER_MEDIA_PATH, ask_for_media_file),
            (Get.FROM_USER_MODE_PARAMS, ask_for_mode_params),
            (Get.FROM_USER_HARMONY_PARAMS, ask_for_harmony_params),
            (Get.FROM_USER_PDF_PATH, ask_for_pdf_file),
            (Get.FROM_USER_RETRY_MEDIA_PATH, ask_retry_media_file),
            (Get.FROM_USER_RETRY_PDF_PATH, ask_retry_pdf_file),
            (Get.FROM_USER_ADD_TIMELINE_WITHOUT_MEDIA, ask_add_timeline_without_media),
            (Get.FROM_USER_BEAT_TIMELINE_FILL_METHOD, ask_beat_timeline_fill_method),
        }

        for request, callback in SERVES:
            serve(self, request, callback)
