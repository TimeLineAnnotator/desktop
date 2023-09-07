import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def get_tilia_class_string(self: Any) -> str:
    return self.__class__.__name__ + "-" + str(id(self))


def open_with_os(path: Path) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    if sys.platform == "win32":
        print(path.resolve())
        subprocess.Popen(["start", path.resolve()], shell=True)
    elif sys.platform == "linux":
        subprocess.Popen(["xdg-open", str(path)])  # shell=True breaks command on linux
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path.resolve()], shell=True)
    else:
        raise OSError(f"Unsupported platform: {sys.platform}")
