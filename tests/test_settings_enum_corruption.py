from PySide6.QtCore import QByteArray

from tilia.settings import settings
from tilia.ui.enums import ScrollType

# The value a crashed run leaves behind: QSettings' @Variant wrapper around a
# truncated pickle of a PyObject (an enum), from issue #711.
CORRUPT_PICKLED_ENUM = QByteArray(
    b"@Variant(\x00\x00\x00\x7f\x00\x00\x00\tPyObject\x00"
)

KEY = "editable/general/auto-scroll"


def _reset_store_to_defaults():
    settings._settings.clear()
    settings._cache = {}
    settings._check_all_default_settings_present()


class TestEnumSettingsSurviveRestart:
    """A process that exits can leave an enum default stored as a pickled
    PyObject. The next run must not crash reading it (#711), and healthy
    stores must hold plain ints so no pickle is written in the first place.
    """

    def test_auto_scroll_default_is_stored_as_a_plain_int(self):
        _reset_store_to_defaults()

        raw = settings._settings.value(KEY)

        assert raw == ScrollType.OFF.value
        assert not isinstance(raw, ScrollType)

    def test_corrupt_pickled_value_falls_back_to_default(self):
        settings._settings.setValue(KEY, CORRUPT_PICKLED_ENUM)
        settings._settings.sync()
        settings._cache = {}

        # Used to raise "EOFError: Ran out of input" during
        # _check_all_default_settings_present, crashing the app on startup.
        _reset_store_to_defaults()

        assert settings.get("general", "auto-scroll") == ScrollType.OFF.value
