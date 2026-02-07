from contextlib import contextmanager
from unittest.mock import patch

from tilia.requests import get, Get
from tilia.ui.cli import io


def get_timeline_by_name(name: str):
    tls = get(Get.TIMELINES_BY_ATTR, "name", name)

    if not tls:
        io.error(f"No timeline found with name={name}")
        return False, None
    if len(tls) == 1:
        return True, tls[0]
    else:  # len(tls) > 1
        io.warn(f"There is more than one timeline with name '{name}'")
        return True, tls[0]


def get_timeline_by_ordinal(ordinal: int):
    tl = get(Get.TIMELINE_BY_ATTR, "ordinal", ordinal)

    if not tl:
        io.error(f"No timeline found with ordinal={ordinal}")
        return False, None
    else:
        return True, tl


@contextmanager
def patch_warn():
    with patch("tilia.ui.cli.io.warn") as mock_warn:
        yield mock_warn


@contextmanager
def assert_warn():
    with patch("tilia.ui.cli.io.warn") as mock_warn:
        yield mock_warn

    mock_warn.assert_called()


@contextmanager
def patch_error():
    with patch("tilia.ui.cli.io.error") as mock_warn:
        yield mock_warn


@contextmanager
def assert_error():
    with patch("tilia.ui.cli.io.error") as mock_error:
        yield mock_error

    mock_error.assert_called()
