from contextlib import contextmanager
from unittest.mock import patch

from colorama import Fore

from tilia.requests import get, Get
from tilia.ui.cli import io


def get_timeline_by_name(name: str):
    tl = get(Get.TIMELINE_BY_ATTR, "name", name)

    if not tl:
        io.output(f"No timeline found with name={name}", Fore.RED)
        return False, None
    else:
        return True, tl


def get_timeline_by_ordinal(ordinal: int):
    tl = get(Get.TIMELINE_BY_ATTR, "ordinal", ordinal)

    if not tl:
        io.output(f"No timeline found with ordinal={ordinal}", Fore.RED)
        return False, None
    else:
        return True, tl


@contextmanager
def patch_warn():
    with patch("tilia.ui.cli.io.warn") as mock_warn:
        yield mock_warn
