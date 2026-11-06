import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests import (
    SETTINGS_DIR,
    SETTINGS_DIR_PREFIX,
    SETTINGS_ROOT_VAR,
    is_in_settings_dir,
)
from tilia.constants import APP_NAME
from tilia.settings import STORE_NAME, settings

PERIODICITY = ("beat_timeline", "display_measure_periodicity")
DEFAULT_PERIODICITY = 4
CHANGED_FILE = "changed-by-previous-test.tla"
CRASH_VAR = "TILIA_TEST_CRASH_WORKER"


class TestSettingsIsolation:
    """Settings are backed by a real QSettings store, so anything a test writes
    outlives it unless the suite isolates and restores the store. Without that,
    a value set here leaks into later tests, into the other xdist workers and
    into subsequent runs.

    Under -n auto the last two tests may run in different workers, so
    test_test_session_leaves_no_settings_behind runs them in one.
    """

    def test_settings_are_not_stored_in_the_users_own_store(self):
        assert is_in_settings_dir(settings._settings.fileName())

    @pytest.mark.parametrize(
        "path, expected",
        [
            (os.path.join(SETTINGS_DIR, "TiLiA", "Desktop Settings.ini"), True),
            (SETTINGS_DIR.swapcase() + "/x.ini", os.path.normcase("A") == "a"),
            (SETTINGS_DIR + "-other/x.ini", False),
            (r"\HKEY_CURRENT_USER\Software\TiLiA\Desktop Settings", False),
        ],
        ids=["inside", "other case", "sibling with same prefix", "registry"],
    )
    def test_is_in_settings_dir(self, path, expected):
        assert is_in_settings_dir(path) is expected

    def test_setting_starts_at_its_default(self):
        assert settings.get(*PERIODICITY) == DEFAULT_PERIODICITY

    def test_setting_can_be_changed(self):
        settings.set(*PERIODICITY, 7)
        settings.update_recent_files(CHANGED_FILE, b"", b"")
        assert settings.get(*PERIODICITY) == 7
        assert CHANGED_FILE in settings.get_recent_files()

    def test_setting_changed_by_previous_test_was_restored(self):
        assert settings.get(*PERIODICITY) == DEFAULT_PERIODICITY
        assert CHANGED_FILE not in settings.get_recent_files()


@pytest.mark.skipif(
    CRASH_VAR not in os.environ,
    reason="only runs inside test_test_session_leaves_no_settings_behind",
)
def test_worker_crash():
    os._exit(1)


USERS_SETTINGS = "[General]\nmine=1\n"


@pytest.mark.skipif(
    sys.platform != "linux",
    reason="only on Linux do the user's settings follow XDG_CONFIG_HOME",
)
@pytest.mark.timeout(60)
def test_test_session_leaves_no_settings_behind(tmp_path):
    """Run the tests above in a pytest session of its own, with one xdist
    worker that crashes at the end. The xdist controller runs no tests, and so
    no fixtures. One test, so that the session runs once even under -n auto.
    """
    config_home = tmp_path / "config"
    users_settings = config_home / APP_NAME / f"{STORE_NAME}.conf"
    users_settings.parent.mkdir(parents=True)
    users_settings.write_text(USERS_SETTINGS)
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("PYTEST_") and k != SETTINGS_ROOT_VAR
    }
    env.update(
        XDG_CONFIG_HOME=str(config_home), TMPDIR=str(temp_dir), **{CRASH_VAR: "1"}
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-n",
            "1",
            "-p",
            "no:cacheprovider",
            f"--basetemp={tmp_path / 'basetemp'}",
            f"{__file__}::TestSettingsIsolation",
            f"{__file__}::test_worker_crash",
        ],
        cwd=Path(__file__).parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=50,
    )

    assert "1 failed, 4 passed" in result.stdout, result.stdout + result.stderr
    assert list(users_settings.parent.iterdir()) == [users_settings]
    assert users_settings.read_text() == USERS_SETTINGS
    assert not list(temp_dir.glob(f"{SETTINGS_DIR_PREFIX}*"))
