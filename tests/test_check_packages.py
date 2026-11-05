"""scripts/check_packages.py tests each package with what its own dev group
lists, read from its pyproject.toml, never from a copy that could drift."""

import importlib.util
import venv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script():
    path = ROOT / "scripts" / "check_packages.py"
    spec = importlib.util.spec_from_file_location("check_packages", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", ["tilia-core", "tilia-library"])
def test_a_package_is_tested_with_its_own_dev_group(name, tmp_path, monkeypatch):
    script = load_script()
    commands = []
    monkeypatch.setattr(script, "run", lambda args, cwd, label: commands.append(args))
    monkeypatch.setattr(venv, "create", lambda *args, **kwargs: None)
    wheel = tmp_path / "package.whl"
    script.check_package(name, [wheel], tmp_path)
    install = next(args for args in commands if str(wheel) in args)
    group = f"{ROOT / 'packages' / name / 'pyproject.toml'}:dev"
    # The wheels, and the dev group as pip reads it: nothing else.
    assert install[1:] == ["-m", "pip", "install", "--group", group, str(wheel)]
    # A fresh environment's pip can predate --group, which pip 25.1 added.
    upgrade = [install[0], "-m", "pip", "install", "--upgrade", "pip>=25.1"]
    assert upgrade in commands[: commands.index(install)]
