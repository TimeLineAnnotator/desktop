from pathlib import Path
import tomlkit
from tilia import dirs

with open(Path(dirs.get_build_path(), "settings.toml")) as f:
    default_settings = tomlkit.load(f)

_settings = default_settings
_settings_path = ""


def load(settings_path: Path):

    with open(settings_path, "r") as f:
        loaded_settings = tomlkit.load(f)

    global _settings, _settings_path
    _settings = loaded_settings
    _settings_path = settings_path


def get(table: str, name: str, default_value=None):
    try:
        return _settings[table][name]
    except KeyError:
        return default_value


def edit(table: str, name: str, value) -> None:
    _settings[table][name] = value
    _save()


def _save():
    with open(_settings_path, "w") as f:
        tomlkit.dump(_settings, f)