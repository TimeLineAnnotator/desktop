from pathlib import Path
import tomlkit

from tilia.utils import open_with_os

DEFAULT_SETTINGS = {
    "general": {
        "auto-scroll": False,
        "window_width": 800,
        "window_height": 400,
        "window_x": 20,
        "window_y": 10,
        "timeline_bg": "#EEE",
    },
    "auto-save": {"max_saved_files": 100, "interval": 300},
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
            "notes",
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
        "wave_color": "#3399FF",
        "max_div": 2500
    },
    "beat_timeline": {"display_measure_periodicity": 4, "default_height": 35},
    "hierarchy_timeline": {
        "default_height": 120,
        "hierarchy_default_colors": [
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
        "hierarchy_base_height": 25,
        "hierarchy_level_height_diff": 25,
        "hierarchy_marker_height": 10,
    },
    "marker_timeline": {
        "default_height": 30,
        "marker_width": 8,
        "marker_height": 10,
        "marker_default_color": "#999999",
    },
    "PDF_timeline": {
        "default_height": 30,
    },
    "harmony_timeline": {"default_harmony_display_mode": "chord"},
    "playback": {"ffmpeg_path": ""},
    "dev": {"log_events": False, "log_requests": False, "dev_mode": False},
}

_settings = DEFAULT_SETTINGS
_settings_path = Path()


def load(settings_path: Path):
    with open(settings_path, "r") as f:
        loaded_settings = tomlkit.load(f)

    global _settings, _settings_path
    _settings = loaded_settings
    _settings_path = settings_path


def get(table_name: str, setting: str):
    try:
        table = _settings[table_name]
    except KeyError:
        _set_default_table(table_name)
        return get(table_name, setting)

    try:
        return table[setting]
    except KeyError:
        _set_default_setting(table_name, setting)
        return get(table, setting)


def edit(table: str, name: str, value) -> None:
    _settings[table][name] = value
    _save()


def _save():
    with open(_settings_path, "w") as f:
        tomlkit.dump(_settings, f)


def _set_default_setting(table, name):
    edit(table, name, DEFAULT_SETTINGS[table][name])


def _set_default_table(table):
    _settings[table] = DEFAULT_SETTINGS[table]
    _save()


def open_settings_on_os():
    open_with_os(_settings_path)
