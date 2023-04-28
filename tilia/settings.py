from pathlib import Path
import tomlkit

DEFAULT_SETTINGS = """
[general]
auto-scroll = false
window_width = 800
window_height = 400
window_x = 20
window_y = 10

[auto-save]
max_saved_files = 100
interval = 300

[media_metadata]
default_fields = [
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
    "notes"
]

[slider_timeline]
default_height = 25
trough_radius = 5
trough_color = "#FF0000"
line_color = "#000000"
line_weight = 3

[beat_timeline]
display_measure_periodicity = 5

[hierarchy_timeline]
default_height = 120
hierarchy_default_colors = [
        "#68de7c",
        "#f2d675",
        "#ffabaf",
        "#dcdcde",
        "#9ec2e6",
        "#00ba37",
        "#dba617",
        "#f86368",
        "#a7aaad",
        "#4f94d4"
    ]
hierarchy_base_height = 25
hierarchy_level_height_diff = 25
hierarchy_marker_height = 10

[marker_timeline]
default_height = 30
marker_width = 8
marker_height = 10
marker_default_color = '#999999'

[dev]
log_events = false
dev_mode = false
"""

_settings = tomlkit.loads(DEFAULT_SETTINGS)
_settings_path = Path()


def load(settings_path: Path):

    with open(settings_path, "r") as f:
        loaded_settings = tomlkit.load(f)

    global _settings, _settings_path
    _settings = loaded_settings
    _settings_path = settings_path


def get(table: str, name: str):
    try:
        return _settings[table][name]
    except KeyError:
        _create_entry(table, name)
        return get(table, name)


def edit(table: str, name: str, value) -> None:
    _settings[table][name] = value
    _save()


def _save():
    with open(_settings_path, "w") as f:
        tomlkit.dump(_settings, f)


def _create_entry(table, name):
    default_settings = tomlkit.loads(DEFAULT_SETTINGS)
    edit(table, name, default_settings[table][name])
