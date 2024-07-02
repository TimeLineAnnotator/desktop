import pytest

from tilia.settings import settings


def test_get_missing_setting_gets_default():
    settings.set("dev", "dev_mode", None)

    assert (
        settings.get("dev", "dev_mode") == settings.DEFAULT_SETTINGS["dev"]["dev_mode"]
    )


def test_get_non_existent_setting_raises_error():
    with pytest.raises(KeyError):
        settings.get("dev", "nonsense")


def test_get_missing_table_gets_default():
    settings._settings.pop("dev")

    assert (
        settings.get("dev", "dev_mode") == settings.DEFAULT_SETTINGS["dev"]["dev_mode"]
    )


def test_get_non_existent_table_raises_error():
    with pytest.raises(KeyError):
        settings.get("nonsense", "whatever")
