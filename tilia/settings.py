from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QSettings

import tilia.constants
from tilia.ui.enums import ScrollType


class _Unreadable:
    """A stored value that can't be read as its default's type."""


UNREADABLE = _Unreadable()


class SettingsManager(QObject):
    # Bump VERSION when a setting's name, group or type changes, and add a
    # function to MIGRATIONS that moves version VERSION - 1 to VERSION.
    # Settings are migrated, never reset. Version 0 is both a store saved
    # before settings were versioned and a new, empty one, so a migration
    # must allow for the settings it moves being missing.
    VERSION = 1
    VERSION_KEY = "meta/settings_version"
    MIGRATIONS: dict[int, Callable[[QSettings], None]] = {}

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
            "merge_separator": "|",
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
        "range_timeline": {
            "default_row_height": 30,
            "bottom_margin": 20,
            "default_range_color": "#A0A0A0",
            "range_alpha": 125,
            "handle_color": "#000000",
            "handle_width": 4,
            "default_range_size": 2,
            "default_label_alignment": "left",
            "merge_separator": "|",
            "always_show_extensions": "false",
            "split_all_rows": "false",
        },
        "PDF_timeline": {
            "default_height": 30,
        },
        "harmony_timeline": {"default_harmony_display_mode": "roman"},
        "dev": {"log_requests": "false", "max_stored_logs": 100},
    }

    def __init__(self, qsettings: QSettings | None = None):
        super().__init__()
        if qsettings is None:
            qsettings = QSettings(
                tilia.constants.APP_NAME, application="Desktop Settings", parent=None
            )
        self._settings = qsettings
        self._files_updated_callbacks = set()
        self._cache = {}
        self._migrate()
        self._check_all_default_settings_present()

    def _stored_version(self) -> int:
        value = self._settings.value(self.VERSION_KEY, None)
        if value is None:
            return 0  # saved before settings were versioned
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _migrate(self) -> None:
        version = self._stored_version()
        if version > self.VERSION:
            # Saved by a newer TiLiA: read what we understand, change nothing.
            return
        for from_version in range(version, self.VERSION):
            if migration := self.MIGRATIONS.get(from_version):
                migration(self._settings)
        self._settings.setValue(self.VERSION_KEY, self.VERSION)

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
        self._settings.endGroup()
        self._check_all_default_settings_present()

    def _clear_recent_files(self):
        self._settings.beginGroup("private")
        self._settings.remove("")
        self._settings.endGroup()

    def link_file_update(self, updating_function) -> None:
        self._files_updated_callbacks.add(updating_function)

    def _get(self, group_name: str, setting: str, in_default=True):
        try:
            default = self.DEFAULT_SETTINGS[group_name][setting]
        except KeyError:
            return None
        key = self._get_key(group_name, setting, in_default)

        # Only a missing value is missing. Zero, empty text and empty lists
        # are values the user chose.
        if not self._settings.contains(key):
            self._settings.setValue(key, default)
            return self._as_setting(default, default)

        try:
            stored = self._settings.value(key, None)
        except EOFError:
            # A pickled value (an enum) that can't be loaded: nothing can read
            # it, so replace it.
            self._settings.setValue(key, default)
            return self._as_setting(default, default)

        value = self._as_setting(stored, default)
        if value is UNREADABLE:
            # Keep the stored value, so that a version that can read it
            # (an older or newer TiLiA) still finds it.
            return self._as_setting(default, default)
        return value

    @staticmethod
    def _as_setting(value: Any, default: Any) -> Any:
        """Reads a stored value with its default's type.

        INI files (Linux) store every value as text, and a list of one item
        as that item; an empty list reads back as None. The Windows registry
        stores booleans as text. Booleans have "true" or "false" as defaults.
        """
        if isinstance(default, str) and default.lower() in ("true", "false"):
            if isinstance(value, bool):
                return value
            if isinstance(value, str) and value.lower() in ("true", "false"):
                return value.lower() == "true"
            return UNREADABLE

        if isinstance(default, int):
            if isinstance(value, int) and not isinstance(value, bool):
                return value
            if isinstance(value, str):
                try:
                    return int(value)
                except ValueError:
                    return UNREADABLE
            return UNREADABLE

        if isinstance(default, list):
            if value is None:
                return []
            if isinstance(value, str):
                return [value]
            if isinstance(value, list):
                return value
            return UNREADABLE

        if isinstance(default, str):
            return value if isinstance(value, str) else UNREADABLE

        return value if isinstance(value, type(default)) else UNREADABLE

    def _set(self, group_name: str, setting: str, value, in_default=True):
        key = self._get_key(group_name, setting, in_default)
        self._settings.setValue(key, value)

    def get(self, group_name: str, setting: str):
        return self._cache[group_name][setting]

    def set(self, group_name: str, setting: str, value):
        try:
            self._cache[group_name][setting] = value
            self._set(group_name, setting, value)
        except AttributeError as e:
            raise AttributeError(f"{group_name}.{setting} not found in cache.") from e

    @staticmethod
    def _get_key(group_name: str, setting: str, in_default: bool) -> str:
        return f"{'editable/' if in_default else ''}{group_name}/{setting}"

    def update_recent_files(
        self,
        path,
        geometry,
        state,
        zoom: float | None = None,
        time: float | None = None,
    ):
        recent_files = self._settings.value("private/recent_files", [])
        if not isinstance(recent_files, list):
            recent_files = [recent_files]
        path = Path(path).as_posix()
        if path in recent_files:
            recent_files.remove(path)
        recent_files.insert(0, path)
        self._settings.setValue("private/recent_files", recent_files)
        self._settings.setValue(f"private/recent_files/{path}/geometry", geometry)
        self._settings.setValue(f"private/recent_files/{path}/state", state)
        if zoom is not None:
            self._settings.setValue(f"private/recent_files/{path}/zoom", zoom)
        if time is not None:
            self._settings.setValue(f"private/recent_files/{path}/playback_time", time)
        self._apply_recent_files_changes()

    def get_file_geometry(self, path) -> tuple:
        path = Path(path).as_posix()
        geometry = self._settings.value(f"private/recent_files/{path}/geometry", None)
        state = self._settings.value(f"private/recent_files/{path}/state", None)
        return geometry, state

    def get_file_zoom(self, path) -> float | None:
        path = Path(path).as_posix()
        zoom = self._settings.value(f"private/recent_files/{path}/zoom", None)
        return float(zoom) if zoom is not None else None

    def get_file_time(self, path) -> float | None:
        path = Path(path).as_posix()
        value = self._settings.value(f"private/recent_files/{path}/playback_time", None)
        return float(value) if value is not None else None

    def remove_from_recent_files(self, path):
        recent_files = self._settings.value("private/recent_files", [])
        path = Path(path).as_posix()
        if path in recent_files:
            recent_files.remove(path)
        self._settings.setValue("private/recent_files", recent_files)
        self._apply_recent_files_changes()

    def _apply_recent_files_changes(self):
        for function in self._files_updated_callbacks:
            function()

    def get_recent_files(self):
        return self._settings.value("private/recent_files", [])[:10]

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
