import os
import sys
import subprocess
from pathlib import Path


def os_run(path: Path) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(f"File not found: {path}")

    if sys.platform == "win32":
        print(path.resolve())
        subprocess.Popen(["start", path.resolve()], shell=True)
    elif sys.platform == "linux":
        subprocess.Popen(["xdg-open", path.resolve()], shell=True)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path.resolve()], shell=True)
    else:
        raise OSError(f"Unsupported platform: {sys.platform}")
