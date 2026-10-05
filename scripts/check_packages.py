"""Check that the packages in ``packages/`` install and test without Qt.

Builds the wheels of tilia-core and tilia-library, installs each into a fresh
virtual environment (the library with the core wheel from this checkout), checks
that neither PySide6 nor the TiLiA app (``tilia``) is importable there, and runs
the package's tests with that environment's interpreter.

Run it with any Python from 3.10 on: ``python scripts/check_packages.py``.
Exits with 0 if every step passed and 1 at the first failure.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
FORBIDDEN = ("PySide6", "shiboken6", "tilia")

FIND_SPEC = (
    "import importlib.util, sys\n"
    "found = [n for n in sys.argv[1:] if importlib.util.find_spec(n) is not None]\n"
    "print(' '.join(found))\n"
    "sys.exit(1 if found else 0)\n"
)


class StepFailed(Exception):
    pass


def run(args: list[str], cwd: Path, label: str) -> None:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise StepFailed(
            f"FAILED: {label}\n"
            f"command: {' '.join(args)}\n"
            f"{result.stdout}{result.stderr}"
        )
    print(f"ok: {label}", flush=True)


def env_python(env: Path) -> str:
    if sys.platform == "win32":
        return str(env / "Scripts" / "python.exe")
    return str(env / "bin" / "python")


def pip_python(tmp: Path) -> str:
    """Return an interpreter that has pip: the running one, else a fresh venv's."""
    probe = subprocess.run(
        [sys.executable, "-m", "pip", "--version"], capture_output=True, text=True
    )
    if probe.returncode == 0:
        return sys.executable
    env = tmp / "env-builder"
    venv.create(env, with_pip=True)
    return env_python(env)


def check_package(name: str, wheels: list[Path], tmp: Path) -> None:
    env = tmp / f"env-{name}"
    venv.create(env, with_pip=True)
    python = env_python(env)
    run(
        [python, "-m", "pip", "install", "pytest", *map(str, wheels)],
        tmp,
        f"{name}: install into a fresh environment",
    )
    probe_cwd = tmp / f"probe-{name}"
    probe_cwd.mkdir()
    run(
        [python, "-c", FIND_SPEC, *FORBIDDEN],
        probe_cwd,
        f"{name}: PySide6 and the app are absent",
    )
    run(
        [python, "-m", "pytest", "-p", "no:cacheprovider"],
        PACKAGES / name,
        f"{name}: tests pass",
    )


def main() -> int:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_name:
        tmp = Path(tmp_name)
        wheel_dir = tmp / "wheels"
        try:
            run(
                [
                    pip_python(tmp),
                    "-m",
                    "pip",
                    "wheel",
                    "--no-deps",
                    "--wheel-dir",
                    str(wheel_dir),
                    str(PACKAGES / "tilia-core"),
                    str(PACKAGES / "tilia-library"),
                ],
                ROOT,
                "build both wheels",
            )
            core = next(wheel_dir.glob("tilia_core-*.whl"))
            library = next(wheel_dir.glob("tilia_library-*.whl"))
            check_package("tilia-core", [core], tmp)
            check_package("tilia-library", [core, library], tmp)
        except StepFailed as error:
            print(error)
            return 1
    print("All package checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
