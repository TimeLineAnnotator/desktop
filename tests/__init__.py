import tempfile

from PySide6.QtCore import QSettings

# Every test process, the xdist controller included, keeps its settings in a
# directory of its own, so that no test reads or writes the developer's
# settings, or another process's. QSettings.setPath() can move ini files, but
# not the native stores of macOS and Windows, so settings are stored in an ini
# file. This has to run before anything imports tilia.settings, and pytest
# imports this package before conftest.py. conftest.py removes the directory
# at the end of the session.
SETTINGS_DIR_PREFIX = "tilia-test-settings-"
SETTINGS_DIR = tempfile.mkdtemp(prefix=SETTINGS_DIR_PREFIX)
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, SETTINGS_DIR)
