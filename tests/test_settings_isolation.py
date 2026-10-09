import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests import SETTINGS_DIR
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
        assert Path(settings._settings.fileName()).is_relative_to(SETTINGS_DIR)

    def test_setting_starts_at_its_default(self):
        assert settings.get(*PERIODICITY) == DEFAULT_PERIODICITY

    def test_setting_can_be_changed(self):
        settings.set(*PERIODICITY, 7)
        assert settings.get(*PERIODICITY) == 7

    def test_setting_changed_by_previous_test_was_restored(self):
        assert settings.get(*PERIODICITY) == DEFAULT_PERIODICITY


USERS_SETTINGS = "[General]\nmine=1\n"


@pytest.fixture(scope="module")
def finished_session(tmp_path_factory):
    """Run a test that changes a setting in a pytest session of its own, with
    an xdist worker. The xdist controller runs no tests, and so no fixtures.
    Returns the directories the session used for the user's settings and for
    temporary files.
    """
    root = tmp_path_factory.mktemp("session")
    config_home = root / "config"
    users_settings = config_home / "TiLiA" / "Desktop Settings.conf"
    users_settings.parent.mkdir(parents=True)
    users_settings.write_text(USERS_SETTINGS)
    temp_dir = root / "temp"
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
            f"--basetemp={root / 'basetemp'}",
            f"{__file__}::TestSettingsIsolation::test_setting_can_be_changed",
        ],
        cwd=Path(__file__).parents[1],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    return config_home, temp_dir


@pytest.mark.skipif(
    sys.platform != "linux",
    reason="only on Linux do the user's settings follow XDG_CONFIG_HOME",
)
@pytest.mark.timeout(60)
class TestTestSession:
    def test_users_settings_are_left_alone(self, finished_session):
        config_home, _ = finished_session
        users_settings = config_home / "TiLiA" / "Desktop Settings.conf"
        assert list(users_settings.parent.iterdir()) == [users_settings]
        assert users_settings.read_text() == USERS_SETTINGS

    def test_settings_directories_are_removed(self, finished_session):
        _, temp_dir = finished_session
        assert not list(temp_dir.glob("tilia-test-settings-*"))
