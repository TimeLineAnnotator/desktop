from PyQt6.QtCore import QSettings, QObject

import tilia.constants
from tilia.ui.enums import ScrollType


class SettingsManager(QObject):

    DEFAULT_SETTINGS = {
        "general": {
            "auto-scroll": ScrollType.OFF,
            "window_width": 800,
            "window_height": 400,
            "window_x": 20,
            "window_y": 10,
            "timeline_background_color": "#EEE",
            "loop_box_shade": "#78c0c0c0",
            "prioritise_performance": "true",
        },
        "auto-save": {"max_stored_files": 100, "interval_(seconds)": 300},
        "media_metadata": {
            "default_fields": [
                "composer",
                "tonality",
                "time signature",
                "performer",
                "performance year",
                "arranger",
                "composition year",
                "recording year",
                "form",
                "instrumentation",
                "genre",
                "lyrics",
            ],
            "window_width": 400,
        },
        "slider_timeline": {
            "default_height": 40,
            "trough_radius": 5,
            "trough_color": "#FF0000",
            "line_color": "#cccccc",
            "line_weight": 5,
        },
        "audiowave_timeline": {
            "default_height": 80,
            "default_color": "#3399FF",
            "max_divisions": 2500,
        },
        "beat_timeline": {"display_measure_periodicity": 4, "default_height": 35},
        "hierarchy_timeline": {
            "default_height": 120,
            "default_colors": [
                "#ff964f",
                "#68de7c",
                "#f2d675",
                "#ffabaf",
                "#dcdcde",
                "#9ec2e6",
                "#00ba37",
                "#dba617",
                "#f86368",
                "#a7aaad",
                "#4f94d4",
            ],
            "base_height": 25,
            "level_height_diff": 25,
            "divider_height": 10,
            "prompt_create_level_below": "true",
        },
        "marker_timeline": {
            "default_height": 30,
            "marker_width": 8,
            "marker_height": 10,
            "default_color": "#999999",
        },
        "score_timeline": {
            "default_height": 160,
            "note_height": 12,
            "default_note_color": "#000000",
            "measure_tracker_color": "#80ff8000",
        },
        "PDF_timeline": {
            "default_height": 30,
        },
        "harmony_timeline": {"default_harmony_display_mode": "roman"},
        "dev": {"log_requests": "false", "max_stored_logs": 100},
    }

    def __init__(self):
        self._settings = QSettings(tilia.constants.APP_NAME, "Desktop Settings")
        self._files_updated_callbacks = set()
        self._cache = {}
        self._check_all_default_settings_present()

    def _check_all_default_settings_present(self):
        for group_name, setting in self.DEFAULT_SETTINGS.items():
            for name in setting.keys():
                if group_name not in self._cache.keys():
                    self._cache[group_name] = {}
                self._cache[group_name][name] = self._get(group_name, name)

    def reset_to_default(self):
        self._cache = {}
        self._settings.beginGroup("editable")
        self._settings.remove("")
        self._check_all_default_settings_present()
        self._settings.endGroup()

    def _clear_recent_files(self):
        self._settings.beginGroup("private")
        self._settings.remove("")
        self._settings.endGroup()

    def link_file_update(self, updating_function) -> None:
        self._files_updated_callbacks.add(updating_function)

    def _get(self, group_name: str, setting: str, in_default=True):
        key = self._get_key(group_name, setting, in_default)
        value = self._settings.value(key, None)
        if not value or not isinstance(
            value, type(self.DEFAULT_SETTINGS[group_name][setting])
        ):
            try:
                value = self.DEFAULT_SETTINGS[group_name][setting]
            except KeyError:
                return None
            self._settings.setValue(key, value)

        # QSettings saves all settings as strings; check typing before parsing
        if isinstance(value, str):
            if value.lower() == "true":
                return True
            elif value.lower() == "false":
                return False
            elif value.isnumeric():
                return int(value)

        return value

    def _set(self, group_name: str, setting: str, value, in_default=True):
        key = self._get_key(group_name, setting, in_default)
        self._settings.setValue(key, value)

    def get(self, group_name: str, setting: str):
        return self._cache[group_name][setting]

    def set(self, group_name: str, setting: str, value):
        try:
            self._cache[group_name][setting] = value
            self._set(group_name, setting, value)
        except AttributeError:
            raise AttributeError(f"{group_name}.{setting} not found in cache.")

    @staticmethod
    def _get_key(group_name: str, setting: str, in_default: bool) -> str:
        return f"{'editable/' if in_default else ''}{group_name}/{setting}"

    def update_recent_files(self, path, geometry, state):
        recent_files = self._settings.value("private/recent_files", [])
        if path in recent_files:
            recent_files.remove(path)
        recent_files.insert(0, path)
        self._settings.setValue("private/recent_files", recent_files)
        self._settings.setValue(f"private/recent_files/{path}/geometry", geometry)
        self._settings.setValue(f"private/recent_files/{path}/state", state)
        self._apply_recent_files_changes()

    def remove_from_recent_files(self, path):
        recent_files = self._settings.value("private/recent_files", [])
        if path in recent_files:
            recent_files.remove(path)
        self._settings.setValue("private/recent_files", recent_files)
        self._apply_recent_files_changes()

    def _apply_recent_files_changes(self):
        for function in self._files_updated_callbacks:
            function()

    def get_recent_files(self):
        return self._settings.value("private/recent_files", [])[:10]

    def get_geometry_and_state_from_path(self, path):
        geometry = self._settings.value(f"private/recent_files/{path}/geometry", None)
        state = self._settings.value(f"private/recent_files/{path}/state", None)
        return geometry, state

    def get_user(self) -> tuple[str, str]:
        email = self._settings.value("private/user/email", "")
        name = self._settings.value("private/user/name", "")
        return email, name

    def set_user(self, email: str, name: str):
        self._settings.setValue("private/user/email", email)
        self._settings.setValue("private/user/name", name)

    def get_dict(self) -> dict:
        return self._cache


settings = SettingsManager()
