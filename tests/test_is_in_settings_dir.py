import os

import pytest

from tests import SETTINGS_DIR, is_in_settings_dir


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
def test_is_in_settings_dir(path, expected):
    assert is_in_settings_dir(path) is expected
