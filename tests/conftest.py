import pytest
from tilia import settings


@pytest.fixture(scope='session', autouse=True)
def setup_test_session():
    prev_dev_mode_value = settings.settings['dev']['dev_mode']
    settings.edit_setting('dev', 'dev_mode', False)
    yield
    settings.edit_setting('dev', 'dev_mode', prev_dev_mode_value)
