import sys

from PyQt6.QtCore import QSettings, QObject

import tilia.constants


class SettingsManager(QObject):

    DEFAULT_SETTINGS = {
        "general": {
            "auto-scroll": "false",
            "window_width": 800,
            "window_height": 400,
            "window_x": 20,
            "window_y": 10,
            "timeline_background_color": "#EEE",
            "loop_box_shade": "#78c0c0c0",
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
        },
        "marker_timeline": {
            "default_height": 30,
            "marker_width": 8,
            "marker_height": 10,
            "default_color": "#999999",
        },
        "PDF_timeline": {
            "default_height": 30,
        },
        "harmony_timeline": {"default_harmony_display_mode": "chord"},
        "dev": {"log_events": "false", "log_requests": "false", "dev_mode": "false"},
    }

    def __init__(self):
        self._settings = QSettings(
            tilia.constants.APP_NAME, f"Desktop-v.{tilia.constants.VERSION}"
        )
        self.check_all_default_settings_present()
        self._files_updated_callbacks = set()

    def check_all_default_settings_present(self):
        for group_name, setting in self.DEFAULT_SETTINGS.items():
            for name in setting.keys():
                self.get(group_name, name)

    def reset_to_default(self):
        self._settings.beginGroup("editable")
        self._settings.remove("")
        for group, settings in self.DEFAULT_SETTINGS.items():
            self._settings.beginGroup(group)
            for key, value in settings.items():
                self._settings.setValue(key, value)
            self._settings.endGroup()
        self._settings.endGroup()

    def _clear_recent_files(self):
        self._settings.beginGroup("private")
        self._settings.remove("")
        self._settings.endGroup()

    def link_file_update(self, updating_function) -> None:
        self._files_updated_callbacks.add(updating_function)

    def get(self, group_name: str, setting: str, in_default=True):
        key = self._get_key(group_name, setting, in_default)
        value = self._settings.value(key, None)
        if not value:
            try:
                value = self.DEFAULT_SETTINGS[group_name][setting]
            except KeyError:
                return None
            self._settings.setValue(key, value)

        if value == "true":
            return True
        elif value == "false":
            return False
        elif sys.platform == 'linux' and isinstance(value, str) and value.isnumeric():
            # For some reason, PyQt parses numeric values as strings in Linux.
            # Is this a Qt bug?
            return int(value)

        return value

    def set(self, group_name: str, setting: str, value, in_default=True):
        key = self._get_key(group_name, setting, in_default)
        self._settings.setValue(key, value)

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

    def get_dict(self) -> dict:
        editable_settings = {}
        self._settings.beginGroup("editable")
        for group_name in self._settings.childGroups():
            self._settings.beginGroup(group_name)
            editable_settings[group_name] = {}
            for setting in self._settings.childKeys():
                editable_settings[group_name][setting] = self._settings.value(setting)
            self._settings.endGroup()
        self._settings.endGroup()
        return editable_settings


settings = SettingsManager()
