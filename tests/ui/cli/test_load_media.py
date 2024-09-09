import shutil
import time

import pytest

from tests.constants import EXAMPLE_OGG_DURATION
from tilia.requests import get, Get


def assert_load_was_successful(duration):
    time.sleep(0.5)
    assert pytest.approx(get(Get.MEDIA_DURATION)) == duration


def test_load_inexistent(cli, tilia_errors):
    cli.run(['load-media', 'inexistent'])

    tilia_errors.assert_error()
    assert 'inexistent' in tilia_errors.errors[0]["message"]


def test_load(cli, tilia_errors, resources):
    path = resources / 'example.ogg'
    cli.run(['load-media', str(path.resolve())])

    assert_load_was_successful(EXAMPLE_OGG_DURATION)


def test_load_with_forward_slashes(cli, tilia_errors, resources):
    path = resources / 'example.ogg'
    path = str(path.resolve()).replace('/', '\\')

    cli.run(['load-media', path])

    assert_load_was_successful(EXAMPLE_OGG_DURATION)


def test_load_with_spaces(cli, tilia_errors, resources, tmp_path):
    path = resources / 'example.ogg'
    shutil.copy(str(path), str(tmp_path / 'with spaces.ogg'))

    cli.run(['load-media', (tmp_path / 'with spaces.ogg').resolve().__str__()])

    assert_load_was_successful(EXAMPLE_OGG_DURATION)



