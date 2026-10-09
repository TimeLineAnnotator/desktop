"""Messages to and from TiLiA windows.

Each TiLiA window tells the library which files it has open and whether each
has unsaved changes. The library skips unsaved files in bulk edits, and queues
an event for every window that has open a file an edit wrote. A window that
stays silent for a lease is forgotten.
"""

from __future__ import annotations

import os
import secrets
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

LEASE_S = 15.0
POLL_S = 2.0


def path_key(path: str | Path) -> str:
    """One key per file, however its path is spelled."""
    return os.path.normcase(str(Path(path).resolve()))


@dataclass
class _OpenFile:
    reported: str  # the path as the window spelled it
    resolved: Path
    unsaved: bool


@dataclass
class _Window:
    last_heard: float
    files: dict[str, _OpenFile] = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)


class Windows:
    """The TiLiA windows the library has heard from, and what they have open."""

    def __init__(
        self,
        *,
        lease: float = LEASE_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._lease = lease
        self._clock = clock
        self._lock = threading.Lock()
        self._windows: dict[str, _Window] = {}
        self._seq = 0

    @staticmethod
    def _files(files: Iterable[tuple[str, bool]]) -> dict[str, _OpenFile]:
        found: dict[str, _OpenFile] = {}
        for path, unsaved in files:
            key = path_key(path)
            previous = found.get(key)
            found[key] = _OpenFile(
                path,
                Path(path).resolve(),
                unsaved or (previous is not None and previous.unsaved),
            )
        return found

    def _forget_silent(self) -> None:
        now = self._clock()
        for window in [
            w
            for w, state in self._windows.items()
            if now - state.last_heard > self._lease
        ]:
            del self._windows[window]

    def _live(self, window: str) -> _Window:
        state = self._windows.get(window)
        if state is None:
            raise KeyError(window)
        state.last_heard = self._clock()
        return state

    def register(self, pid: int, files: Iterable[tuple[str, bool]]) -> str:
        """Add a window with the files it has open; return its new id."""
        with self._lock:
            self._forget_silent()
            window = secrets.token_urlsafe(12)
            self._windows[window] = _Window(self._clock(), self._files(files))
            return window

    def sync(self, window: str, files: Iterable[tuple[str, bool]]) -> list[dict]:
        """Replace the window's files; return and clear its events.

        Raises ``KeyError`` for a window that is unknown or was forgotten.
        """
        with self._lock:
            self._forget_silent()
            state = self._live(window)
            state.files = self._files(files)
            events, state.events = state.events, []
            return events

    def saved(self, window: str, path: str) -> None:
        """Renew the window's lease; ``KeyError`` when it is unknown or forgotten."""
        with self._lock:
            self._forget_silent()
            self._live(window)

    def close(self, window: str) -> None:
        """Forget the window, if it is known."""
        with self._lock:
            self._windows.pop(window, None)
            self._forget_silent()

    def unsaved(self) -> set[Path]:
        """The resolved paths that some live window reports with unsaved changes."""
        with self._lock:
            self._forget_silent()
            return {
                f.resolved
                for state in self._windows.values()
                for f in state.files.values()
                if f.unsaved
            }

    def written(self, paths: Iterable[Path], corpus: str, entry: str) -> None:
        """Queue an event for each live window that has open a file just written."""
        keys = {path_key(p): p for p in paths}
        with self._lock:
            self._forget_silent()
            for state in self._windows.values():
                for key in keys:
                    open_file = state.files.get(key)
                    if open_file is None:
                        continue
                    self._seq += 1
                    state.events.append(
                        {
                            "seq": self._seq,
                            "type": "changed-by-edit",
                            "path": open_file.reported,
                            "corpus": corpus,
                            "entry": entry,
                        }
                    )
