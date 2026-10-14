import subprocess
import sys

PROBE = """
import importlib
import importlib.abc
import pkgutil
import sys

BLOCKED = set(sys.argv[2:])


class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.partition(".")[0] in BLOCKED:
            raise ImportError(f"{fullname} is blocked")
        return None


sys.meta_path.insert(0, Blocker())
package = importlib.import_module(sys.argv[1])
for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
    importlib.import_module(info.name)
"""


QT_AND_APP = ("PySide6", "shiboken6", "tilia")


def probe(tmp_path, *blocked, package="tilia_core"):
    return subprocess.run(
        [sys.executable, "-c", PROBE, package, *blocked],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )


def test_imports_without_qt_or_app(tmp_path):
    result = probe(tmp_path, *QT_AND_APP)
    assert result.returncode == 0, result.stderr


def test_imports_without_the_harmony_extra(tmp_path):
    # music21 is imported only inside the harmony importer's functions.
    result = probe(tmp_path, *QT_AND_APP, "music21")
    assert result.returncode == 0, result.stderr


def test_imports_without_jsonschema(tmp_path):
    # Installed for the tests only: it pulls in a compiled package.
    result = probe(tmp_path, *QT_AND_APP, "jsonschema")
    assert result.returncode == 0, result.stderr


def test_probe_finds_a_module_level_import_of_a_blocked_name(tmp_path):
    # Without this, the probes above would pass whatever the modules import.
    package = tmp_path / "probed"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "harmony.py").write_text("import music21\n")

    result = probe(tmp_path, "music21", package="probed")

    assert result.returncode != 0
    assert "music21 is blocked" in result.stderr
