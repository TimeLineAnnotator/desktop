import importlib.metadata
import sys
from unittest.mock import patch


def test_tilia_metadata_not_found():
    # If tilia.constants was already imported, we must remove it from sys.modules
    # to ensure the module-level code runs again with our mocks.
    if "tilia.constants" in sys.modules:
        del sys.modules["tilia.constants"]

    # 1. Mock Path.exists to return False so it skips the pyproject.toml logic
    with patch("pathlib.Path.exists", return_value=False), patch(
        "importlib.metadata.metadata",
        side_effect=importlib.metadata.PackageNotFoundError,
    ):

        import tilia.constants as constants

        assert constants.APP_NAME == ""
        assert constants.VERSION == "0.0.0"
        assert constants.YEAR == "2022-2026"
        assert constants.AUTHOR == ""
        assert constants.EMAIL == ""


def _reload_constants():
    if "tilia.constants" in sys.modules:
        del sys.modules["tilia.constants"]
    import tilia.constants as constants

    return constants


def test_authors_list_joined_into_author_string():
    constants = _reload_constants()

    assert len(constants.AUTHORS) >= 2
    assert constants.AUTHOR == ", ".join(a for a in constants.AUTHORS if a)


def test_notice_uses_license_name_instead_of_copyright_symbol():
    constants = _reload_constants()

    assert "GNU General Public License v3" in constants.NOTICE
    assert "Copyright ©" not in constants.NOTICE
