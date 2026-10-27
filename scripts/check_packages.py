"""Check that the packages in ``packages/`` install and test without Qt.

Builds the wheels of tilia-core and tilia-library, installs each into a fresh
virtual environment (the library with the core wheel from this checkout), checks
that neither PySide6 nor the TiLiA app (``tilia``) is importable there, and runs
the package's tests with that environment's interpreter.

tilia-core is tested twice: in the environment above, where its optional
``regex`` package is checked to be absent too, and in a second fresh
environment that installs the core wheel with its ``[regex]`` extra, where
``regex`` is checked to be present and in use.

Run it with any Python 3.10 to 3.13: ``python scripts/check_packages.py``.
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

REGEX_IN_USE = (
    "import regex\n"
    "from tilia_core.tql import regexes\n"
    "assert regexes.HAS_TIMEOUT is True, 'tilia_core does not use regex'\n"
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


def requirements_of_tests() -> list[str]:
    deps = ["pytest"]
    if sys.version_info < (3, 11):
        deps.append("tomli")
    return deps


def check_package(
    name: str, wheels: list[Path], tmp: Path, *, optional: tuple[str, ...] = ()
) -> None:
    """Install ``wheels`` into a fresh environment and run the tests of ``name``
    there; ``optional`` names packages that must not be importable there."""
    env = tmp / f"env-{name}"
    venv.create(env, with_pip=True)
    python = env_python(env)
    run(
        [python, "-m", "pip", "install", *requirements_of_tests(), *map(str, wheels)],
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
    if optional:
        run(
            [python, "-c", FIND_SPEC, *optional],
            probe_cwd,
            f"{name}: {', '.join(optional)} is absent",
        )
    run(
        [python, "-m", "pytest", "-p", "no:cacheprovider"],
        PACKAGES / name,
        f"{name}: tests pass",
    )


def check_core_with_regex(core: Path, tmp: Path) -> None:
    """Install the core wheel with its ``[regex]`` extra into a fresh
    environment and run the core's tests there, where the ``regex`` package
    gives regular expressions a time limit."""
    env = tmp / "env-tilia-core-regex"
    venv.create(env, with_pip=True)
    python = env_python(env)
    run(
        # one argument, for Windows: the extra's brackets are no shell syntax
        [python, "-m", "pip", "install", *requirements_of_tests(), f"{core}[regex]"],
        tmp,
        "tilia-core with the regex extra: install into a fresh environment",
    )
    probe_cwd = tmp / "probe-tilia-core-regex"
    probe_cwd.mkdir()
    run(
        [python, "-c", REGEX_IN_USE],
        probe_cwd,
        "tilia-core with the regex extra: regex is installed and in use",
    )
    run(
        [python, "-m", "pytest", "-p", "no:cacheprovider"],
        PACKAGES / "tilia-core",
        "tilia-core with the regex extra: tests pass",
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
            check_package("tilia-core", [core], tmp, optional=("regex",))
            check_core_with_regex(core, tmp)
            check_package("tilia-library", [core, library], tmp)
        except StepFailed as error:
            print(error)
            return 1
    print("All package checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
