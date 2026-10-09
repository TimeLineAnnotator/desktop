import tempfile

from PySide6.QtCore import QSettings

# Every test process, the xdist controller included, keeps its settings in a
# directory of its own, so that no test reads or writes the developer's
# settings, or another process's. Under ENVIRONMENT=test, which pytest-env sets
# before this package is imported, SettingsManager stores settings in an ini
# file. This has to run before anything imports tilia.settings, and pytest
# imports this package before conftest.py. conftest.py removes the directory
# at the end of the session.
SETTINGS_DIR = tempfile.mkdtemp(prefix="tilia-test-settings-")
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, SETTINGS_DIR)
