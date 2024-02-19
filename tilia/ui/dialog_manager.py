from tilia.requests import serve, Get

from tilia.ui.dialogs.file import (
    ask_should_save_changes,
    ask_for_file_to_open,
    ask_for_path_to_save_tilia_file,
    ask_for_tilia_file_to_open,
    ask_for_media_file,
    ask_for_path_to_save_ogg_file,
)
from tilia.ui.dialogs.basic import (
    ask_for_directory,
    ask_for_string,
    ask_for_float,
    ask_for_int,
    ask_for_color,
    ask_yes_or_no,
)
from tilia.ui.dialogs.mode_params import ask_for_mode_params, ask_for_harmony_params
from tilia.ui.timelines.beat.dialogs import ask_for_beat_pattern


class DialogManager:
    def __init__(self):
        serve(
            self,
            Get.FROM_USER_SHOULD_SAVE_CHANGES,
            ask_should_save_changes,
        )
        serve(self, Get.FROM_USER_DIR, ask_for_directory)
        serve(
            self,
            Get.FROM_USER_SAVE_PATH_TILIA,
            ask_for_path_to_save_tilia_file,
        )
        serve(
            self,
            Get.FROM_USER_SAVE_PATH_OGG,
            ask_for_path_to_save_ogg_file,
        )
        serve(
            self,
            Get.FROM_USER_TILIA_FILE_PATH,
            ask_for_tilia_file_to_open,
        )
        serve(self, Get.FROM_USER_FILE_PATH, ask_for_file_to_open),
        serve(self, Get.FROM_USER_STRING, ask_for_string)
        serve(self, Get.FROM_USER_FLOAT, ask_for_float)
        serve(self, Get.FROM_USER_INT, ask_for_int)
        serve(self, Get.FROM_USER_YES_OR_NO, ask_yes_or_no)
        serve(self, Get.FROM_USER_COLOR, ask_for_color)
        serve(self, Get.FROM_USER_BEAT_PATTERN, ask_for_beat_pattern)
        serve(self, Get.FROM_USER_MEDIA_PATH, ask_for_media_file)
        serve(self, Get.FROM_USER_MODE_PARAMS, ask_for_mode_params)
        serve(self, Get.FROM_USER_HARMONY_PARAMS, ask_for_harmony_params)
