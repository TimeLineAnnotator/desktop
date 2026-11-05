"""The app depends on tilia-core, with its harmony extra, installed from this
checkout: the release on PyPI lags behind the code the app reads."""

import importlib
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
IMPORTS_THE_LIBRARY = re.compile(r"^\s*(from|import)\s+tilia_library\b", re.MULTILINE)


def pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_app_requires_the_core_with_its_harmony_extra():
    # Read from what is declared: the app's own music21 would let a harmony pass
    # the rules without the extra.
    assert "tilia-core[harmony]" in pyproject()["project"]["dependencies"]


def test_the_core_comes_from_the_workspace():
    assert pyproject()["tool"]["uv"]["sources"]["tilia-core"] == {"workspace": True}


@pytest.mark.parametrize("module", ["tla", "rules", "timemap"])
def test_a_module_of_the_core_imports(module):
    importlib.import_module(f"tilia_core.{module}")


def test_the_installed_core_is_this_checkouts():
    tilia_core = importlib.import_module("tilia_core")
    assert (
        Path(tilia_core.__file__)
        .resolve()
        .is_relative_to(ROOT / "packages" / "tilia-core")
    )


def test_a_valid_harmony_is_checked():
    # Without music21, this raises CantCheck.
    rules = importlib.import_module("tilia_core.rules")
    assert rules.harmony(60.0, [], {"time": 1.0}) == (True, "")


def test_ci_installs_the_core_just_before_the_app():
    installs = []
    for workflow in (ROOT / ".github" / "workflows").glob("*.yml"):
        lines = workflow.read_text(encoding="utf-8").splitlines()
        for before, line in zip(lines, lines[1:], strict=False):
            words = line.split()
            if "install" in words and "." in words:
                installs.append((workflow.name, before.strip()))

    assert {name for name, _ in installs} >= {"build.yml", "run-tests.yml"}
    for name, before in installs:
        assert before == "pip install -e packages/tilia-core", name


def test_the_build_bundles_the_cores_data_files():
    # Nuitka follows imports, but not a file read through importlib.resources:
    # without the entry, the built app stops when it imports tilia_core.tla.
    config = (ROOT / "tilia.nuitka-package.config.yml").read_text(encoding="utf-8")
    assert '- module-name: "tilia_core.tla"' in config
    assert '- "schemas/*.json"' in config

    core = ROOT / "packages" / "tilia-core" / "src" / "tilia_core"
    data_files = [
        path.relative_to(core)
        for path in core.rglob("*")
        if path.is_file() and path.suffix not in {".py", ".pyc", ".typed"}
    ]
    assert data_files
    assert [path for path in data_files if not path.match("tla/schemas/*.json")] == []


def test_the_app_does_not_depend_on_the_library():
    # The workspace installs tilia-library next to the app, so an import of it
    # would work here and nowhere else.
    dependencies = pyproject()["project"]["dependencies"]
    assert not [name for name in dependencies if name.startswith("tilia-library")]
    assert not [
        path
        for path in (ROOT / "tilia").rglob("*.py")
        if IMPORTS_THE_LIBRARY.search(path.read_text(encoding="utf-8"))
    ]
