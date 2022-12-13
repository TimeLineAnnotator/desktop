from unittest.mock import patch

import pytest
import tomlkit

from tilia import settings


@pytest.fixture(autouse=True)
def use_test_settings():

    TEST_SETTINGS_PATH = 'test_settings.toml'

    with open(TEST_SETTINGS_PATH, 'r') as f:
        settings.settings = tomlkit.load(f)

    with patch('tilia.globals_.SETTINGS_PATH', TEST_SETTINGS_PATH):
        yield

    settings.settings = settings._load_settings()


