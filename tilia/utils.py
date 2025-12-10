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
        subprocess.Popen(["start", path.resolve()], shell=True)
    elif sys.platform == "linux":
        subprocess.Popen(["xdg-open", str(path)])  # shell=True breaks command on linux
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path.resolve()], shell=True)
    else:
        raise OSError(f"Unsupported platform: {sys.platform}")


def load_dotenv() -> None:
    root = Path(__file__).parents[1]
    dotenv_paths = [root / fn for fn in os.listdir(root) if fn.endswith(".env")]

    if dotenv_paths:
        import dotenv

        for p in dotenv_paths:
            with open(p) as f:
                dotenv.load_dotenv(stream=f)

    else:  # setup some basic values
        os.environ["LOG_REQUESTS"] = "1"
        os.environ[
            "EXCLUDE_FROM_LOG"
        ] = "TIMELINE_VIEW_LEFT_BUTTON_DRAG;PLAYER_CURRENT_TIME_CHANGED;APP_RECORD_STATE"
    if not os.environ.get("ENVIRONMENT"):
        os.environ["ENVIRONMENT"] = "dev"
