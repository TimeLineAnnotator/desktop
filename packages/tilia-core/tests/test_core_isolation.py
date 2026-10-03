import subprocess
import sys

PROBE = """
import importlib
import importlib.abc
import pkgutil
import sys

BLOCKED = {"PySide6", "shiboken6", "tilia"}


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


def test_imports_without_qt_or_app(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", PROBE, "tilia_core"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
