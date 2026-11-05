import os
import tempfile

from PySide6.QtCore import QSettings

# Every test process, the xdist controller included, keeps its settings in a
# directory of its own, so that no test reads or writes the developer's
# settings, or another process's. QSettings.setPath() can move ini files, but
# not the native stores of macOS and Windows, so settings are stored in an ini
# file. This has to run before anything imports tilia.settings, and pytest
# imports this package before conftest.py. conftest.py removes the directory
# at the end of the session.
#
# xdist workers inherit the controller's environment, so their directories go
# inside the controller's. A worker that crashes never removes its own, and the
# controller removes it with its own.
SETTINGS_DIR_PREFIX = "tilia-test-settings-"
SETTINGS_ROOT_VAR = "TILIA_TEST_SETTINGS_DIR"
SETTINGS_DIR = tempfile.mkdtemp(
    prefix=SETTINGS_DIR_PREFIX, dir=os.environ.get(SETTINGS_ROOT_VAR)
)
os.environ.setdefault(SETTINGS_ROOT_VAR, SETTINGS_DIR)
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, SETTINGS_DIR)
