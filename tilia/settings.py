import tomlkit

from tilia.globals_ import SETTINGS_PATH


def _load_settings():
    with open(SETTINGS_PATH, "r") as f:
        settings = tomlkit.load(f)

    return settings


settings = _load_settings()


def edit_setting(table: str, name: str, value) -> None:
    settings[table][name] = value
    _save_settings()


def _save_settings():
    with open(SETTINGS_PATH, "w") as f:
        tomlkit.dump(settings, f)
