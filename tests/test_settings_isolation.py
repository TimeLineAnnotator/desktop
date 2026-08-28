from tilia.settings import settings

PERIODICITY = ("beat_timeline", "display_measure_periodicity")
DEFAULT_PERIODICITY = 4


class TestSettingsIsolation:
    """Settings are backed by a real QSettings store, so anything a test writes
    outlives it unless the suite isolates and restores the store. Without that,
    a value set here leaks into later tests, into the other xdist workers and
    into subsequent runs.
    """

    def test_settings_are_not_stored_in_the_users_own_store(self):
        assert settings._settings.fileName().endswith(".ini")

    def test_setting_starts_at_its_default(self):
        assert settings.get(*PERIODICITY) == DEFAULT_PERIODICITY

    def test_setting_can_be_changed(self):
        settings.set(*PERIODICITY, 7)
        assert settings.get(*PERIODICITY) == 7

    def test_setting_changed_by_previous_test_was_restored(self):
        assert settings.get(*PERIODICITY) == DEFAULT_PERIODICITY
