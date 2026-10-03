"""Serve the library on fixture data, to try it by hand or from a browser test.

    python packages/tilia-library/tests/support/serve_fixtures.py [--port N]

Needs ``tilia_library`` to be importable (installed, or on PYTHONPATH).
"""

from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixture_backend import FixtureBackend  # noqa: E402

from tilia_library.server import LibraryServer  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    server = LibraryServer(FixtureBackend(), port=args.port)

    def interrupt(signum: int, frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    print(server.entry_url, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
