import shutil

import pytest
from PySide6.QtCore import QSettings

from tilia.settings import SettingsManager
from tilia.ui.windows.settings import get_value_for_widget, get_widget_for_value

EDITED_VALUES = {
    ("general", "window_width"): 1200,
    ("auto-save", "max_stored_files"): 0,
    ("media_metadata", "default_fields"): [],
    ("hierarchy_timeline", "default_colors"): ["#ff0000"],
    ("general", "prioritise_performance"): False,
    ("hierarchy_timeline", "merge_separator"): "",
}


class Store:
    """A settings store that can be "restarted".

    "native" is the system's own store: the registry on Windows, a plist on
    macOS, an INI file on Linux. "ini" is an INI file on every system, so that
    Linux's format is tested everywhere. Qt caches INI files per process, and
    reading back a file this process wrote gives typed values, as if TiLiA had
    never closed; restarting copies the file to a new path, which Qt reads from
    disk, as a new process would.
    """

    def __init__(self, fmt: str, tmp_path):
        self.fmt = fmt
        self.tmp_path = tmp_path
        self.generation = 0
        self.cleanup()

    def qsettings(self) -> QSettings:
        if self.fmt == "ini":
            return QSettings(
                str(self.tmp_path / f"settings-{self.generation}.ini"),
                QSettings.Format.IniFormat,
            )
        return QSettings("TiLiATests", "SettingsTest")

    def restart(self, settings: QSettings) -> QSettings:
        settings.sync()
        if self.fmt == "ini":
            old = self.tmp_path / f"settings-{self.generation}.ini"
            self.generation += 1
            shutil.copy(old, self.tmp_path / f"settings-{self.generation}.ini")
        return self.qsettings()

    def cleanup(self):
        if self.fmt == "native":
            settings = self.qsettings()
            settings.remove("")
            settings.sync()


@pytest.fixture(params=["ini", "native"])
def store(request, tmp_path):
    store_ = Store(request.param, tmp_path)
    yield store_
    store_.cleanup()


class TestRestart:
    def test_edited_values_survive_a_restart(self, store):
        qsettings = store.qsettings()
        manager = SettingsManager(qsettings)
        for (group, name), value in EDITED_VALUES.items():
            manager.set(group, name, value)

        restarted = SettingsManager(store.restart(qsettings))

        for (group, name), value in EDITED_VALUES.items():
            assert restarted.get(group, name) == value, f"{group}.{name}"

    def test_defaults_on_first_start(self, store):
        manager = SettingsManager(store.qsettings())
        assert manager.get("general", "window_width") == 800
        assert manager.get("general", "prioritise_performance") is True
        assert manager.get("media_metadata", "default_fields")[0] == "composer"

    def test_defaults_survive_a_restart(self, store):
        qsettings = store.qsettings()
        SettingsManager(qsettings)
        restarted = SettingsManager(store.restart(qsettings))
        assert restarted.get("general", "window_width") == 800
        assert restarted.get("general", "prioritise_performance") is True
        assert restarted.get("hierarchy_timeline", "default_colors") == (
            SettingsManager.DEFAULT_SETTINGS["hierarchy_timeline"]["default_colors"]
        )


class TestUnreadableValues:
    def test_falls_back_to_default_without_overwriting(self, store):
        qsettings = store.qsettings()
        qsettings.setValue("editable/general/window_width", "wide")

        manager = SettingsManager(qsettings)

        assert manager.get("general", "window_width") == 800
        assert qsettings.value("editable/general/window_width") == "wide"


class TestVersion:
    def test_version_is_written(self, store):
        qsettings = store.qsettings()
        SettingsManager(qsettings)
        assert int(qsettings.value(SettingsManager.VERSION_KEY)) == (
            SettingsManager.VERSION
        )

    def test_older_settings_are_migrated(self, store, monkeypatch):
        def rename_width(qsettings: QSettings) -> None:
            qsettings.setValue(
                "editable/general/window_width",
                qsettings.value("editable/general/old_width"),
            )
            qsettings.remove("editable/general/old_width")

        monkeypatch.setattr(SettingsManager, "VERSION", 2)
        monkeypatch.setattr(SettingsManager, "MIGRATIONS", {1: rename_width})
        qsettings = store.qsettings()
        qsettings.setValue(SettingsManager.VERSION_KEY, 1)
        qsettings.setValue("editable/general/old_width", 1234)

        manager = SettingsManager(qsettings)

        assert manager.get("general", "window_width") == 1234
        assert not qsettings.contains("editable/general/old_width")
        assert int(qsettings.value(SettingsManager.VERSION_KEY)) == 2

    def test_newer_settings_are_left_alone(self, store):
        qsettings = store.qsettings()
        newer = SettingsManager.VERSION + 1
        qsettings.setValue(SettingsManager.VERSION_KEY, newer)
        qsettings.setValue("editable/general/from_a_newer_version", "kept")

        SettingsManager(qsettings)

        assert int(qsettings.value(SettingsManager.VERSION_KEY)) == newer
        assert qsettings.value("editable/general/from_a_newer_version") == "kept"


class TestResetToDefault:
    def test_resets_edited_values(self, store):
        qsettings = store.qsettings()
        manager = SettingsManager(qsettings)
        manager.set("general", "window_width", 1200)

        manager.reset_to_default()

        assert manager.get("general", "window_width") == 800
        assert int(qsettings.value("editable/general/window_width")) == 800

    def test_writes_defaults_in_their_own_group(self, store):
        qsettings = store.qsettings()
        manager = SettingsManager(qsettings)

        manager.reset_to_default()

        assert not any(
            key.startswith("editable/editable/") for key in qsettings.allKeys()
        )

    def test_keeps_the_version(self, store):
        qsettings = store.qsettings()
        manager = SettingsManager(qsettings)

        manager.reset_to_default()

        assert qsettings.contains(SettingsManager.VERSION_KEY)


class TestSettingsWindow:
    @pytest.mark.parametrize("value", [[], [""]])
    def test_shows_an_empty_list(self, value):
        widget = get_widget_for_value(None, value)
        assert get_value_for_widget(widget) == []
