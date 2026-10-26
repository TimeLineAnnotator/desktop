"""Serve the library on fixture data, to try it by hand or from a browser test.

    python packages/tilia-library/tests/support/serve_fixtures.py [--port N]

Needs ``tilia_library`` to be importable (installed, or on PYTHONPATH).
"""

from __future__ import annotations

import argparse
import shutil
import signal
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixture_backend import FixtureBackend  # noqa: E402

from tilia_library.api import register_all  # noqa: E402
from tilia_library.corpora import Corpora  # noqa: E402
from tilia_library.server import LibraryServer  # noqa: E402


def make_corpora(root: Path) -> Corpora:
    """A library of two folders (the first one last used) and one that is gone."""
    corpora = Corpora(root / "library.toml")
    names = ("Fixture corpus", "Zweites Korpus", "Verschwunden")
    for name in names:
        (root / name).mkdir()
        corpora.add(root / name)
    shutil.rmtree(root / names[2])
    corpora.add(root / names[0])
    return corpora


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    tmp = tempfile.mkdtemp(prefix="tilia-library-")
    server = LibraryServer(FixtureBackend(), port=args.port)
    register_all(server, make_corpora(Path(tmp)))

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
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
