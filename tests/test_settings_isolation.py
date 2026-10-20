import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests import SETTINGS_DIR, SETTINGS_DIR_PREFIX
from tilia.constants import APP_NAME
from tilia.settings import STORE_NAME, settings

PERIODICITY = ("beat_timeline", "display_measure_periodicity")
DEFAULT_PERIODICITY = 4


class TestSettingsIsolation:
    """Settings are backed by a real QSettings store, so anything a test writes
    outlives it unless the suite isolates and restores the store. Without that,
    a value set here leaks into later tests, into the other xdist workers and
    into subsequent runs.
    """

    def test_settings_are_not_stored_in_the_users_own_store(self):
        assert Path(settings._settings.fileName()).is_relative_to(SETTINGS_DIR)

    def test_setting_starts_at_its_default(self):
        assert settings.get(*PERIODICITY) == DEFAULT_PERIODICITY

    def test_setting_can_be_changed(self):
        settings.set(*PERIODICITY, 7)
        assert settings.get(*PERIODICITY) == 7

    def test_setting_changed_by_previous_test_was_restored(self):
        assert settings.get(*PERIODICITY) == DEFAULT_PERIODICITY


USERS_SETTINGS = "[General]\nmine=1\n"


@pytest.mark.skipif(
    sys.platform != "linux",
    reason="only on Linux do the user's settings follow XDG_CONFIG_HOME",
)
@pytest.mark.timeout(60)
def test_test_session_leaves_no_settings_behind(tmp_path):
    """Run a test that changes a setting in a pytest session of its own, with
    an xdist worker. The xdist controller runs no tests, and so no fixtures.
    One test, so that the session runs once even under -n auto.
    """
    config_home = tmp_path / "config"
    users_settings = config_home / APP_NAME / f"{STORE_NAME}.conf"
    users_settings.parent.mkdir(parents=True)
    users_settings.write_text(USERS_SETTINGS)
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env.update(XDG_CONFIG_HOME=str(config_home), TMPDIR=str(temp_dir))

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
            f"{__file__}::TestSettingsIsolation::test_setting_can_be_changed",
        ],
        cwd=Path(__file__).parents[1],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert list(users_settings.parent.iterdir()) == [users_settings]
    assert users_settings.read_text() == USERS_SETTINGS
    assert not list(temp_dir.glob(f"{SETTINGS_DIR_PREFIX}*"))
