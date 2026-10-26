"""Run ``tilia library`` with the state folder and the browser replaced.

    python library_wrapper.py STATE_DIR BROWSER_LOG [command arguments...]

Each URL given to the browser is appended to BROWSER_LOG, one per line.
"""

from __future__ import annotations

import sys
import webbrowser
from pathlib import Path

from tilia_core import state


def main() -> int:
    state_dir = Path(sys.argv[1])
    browser_log = Path(sys.argv[2])
    state.state_dir = lambda: state_dir

    def fake_open(url: str, *args: object, **kwargs: object) -> bool:
        with open(browser_log, "a", encoding="utf-8") as log:
            log.write(url + "\n")
        return True

    webbrowser.open = fake_open
    sys.argv = ["tilia library", *sys.argv[3:]]
    from tilia_library.command import main as command_main

    return command_main()


if __name__ == "__main__":
    raise SystemExit(main())
