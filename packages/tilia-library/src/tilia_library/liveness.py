"""Rescans and generations.

Files change outside the library: TiLiA saves, a sync, a hand edit. The library
rescans every corpus a page has opened in this run, and the pages ask for each
corpus's state to find out whether the index has changed since they showed it.
The scan is the mechanism; there is no file watcher.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from tilia_library.backend import Backend
from tilia_library.corpora import Corpus

logger = logging.getLogger(__name__)

INTERVAL_S = 3.0  # rescan every 3 s ...
SLOW_FACTOR = 10.0  # ... but after a scan that took d seconds, not before 10 × d

_TICK_S = 0.2


@dataclass
class _Watched:
    corpus: Corpus
    handle: object
    due: float
    state: dict[str, Any]
    poked: bool = False
    failed: bool = False  # the last rescan raised; repeats are logged briefly


def _counts(rows: list[dict]) -> dict[str, int]:
    return {
        "files": len(rows),
        "unreadable": sum(1 for r in rows if r.get("state") == "unreadable"),
        "unavailable": sum(1 for r in rows if r.get("state") == "unavailable"),
    }


class Liveness:
    """Rescans the watched corpora and keeps what the pages need to know."""

    def __init__(
        self,
        backend: Backend,
        *,
        interval: float = INTERVAL_S,
        slow_factor: float = SLOW_FACTOR,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._backend = backend
        self._interval = interval
        self._slow_factor = slow_factor
        self._clock = clock
        self._watched: dict[str, _Watched] = {}
        self._lock = threading.Lock()  # never held while calling the backend
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None

    def watch(self, cid: str, corpus: Corpus, handle: object) -> None:
        """Rescan this corpus from now on; watching it again does nothing."""
        with self._lock:
            if cid in self._watched:
                return
        state: dict[str, Any] = {
            "generation": None,
            "scanning": False,
            "available": corpus.path.is_dir(),
            "files": None,
            "unreadable": None,
            "unavailable": None,
            "last_scan": None,
        }
        # The counts are left to ``count`` or the first rescan: reading every
        # file's row here would read them twice when the files route opens the
        # corpus, since it reads them anyway.
        try:
            state["generation"] = self._backend.generation(handle)
        except Exception:
            logger.exception("Reading the state of %s failed", corpus.path)
        with self._lock:
            if cid not in self._watched:
                due = self._clock() + self._interval
                self._watched[cid] = _Watched(corpus, handle, due, state)

    def count(self, cid: str, rows: list[dict]) -> None:
        """Count the corpus's files from rows already read, if it has no counts yet.

        Once counted, the rescans keep the counts up to date, so later rows (which
        a rescan may already have overtaken) change nothing. Unknown ids are
        ignored.
        """
        counts = _counts(rows)
        with self._lock:
            watched = self._watched.get(cid)
            if watched is None or watched.state["files"] is not None:
                return
            watched.state.update(counts)

    def unwatch(self, cid: str) -> None:
        """Stop rescanning this corpus and forget its state; unknown ids are ignored."""
        with self._lock:
            self._watched.pop(cid, None)

    def poke(self, cid: str) -> None:
        """Make the corpus's next rescan due now; unknown ids are ignored."""
        with self._lock:
            watched = self._watched.get(cid)
            if watched is None:
                return
            watched.poked = True
            watched.due = self._clock()

    def tick(self) -> None:
        """Rescan, one after another, every corpus whose rescan is due."""
        with self._lock:
            now = self._clock()
            due = [cid for cid, w in self._watched.items() if w.due <= now]
        for cid in due:
            self._rescan(cid)

    def _rescan(self, cid: str) -> None:
        with self._lock:
            watched = self._watched.get(cid)
            if watched is None:  # unwatched since the tick found it due
                return
            watched.poked = False
            watched.state["scanning"] = True
            known = watched.state["generation"]
            counted = watched.state["files"] is not None
        start = self._clock()
        # Whether the folder is there is known without the backend, so a scan
        # that raises because the folder vanished still updates it.
        update: dict[str, Any] = {"available": watched.corpus.path.is_dir()}
        failed = False
        try:
            self._backend.scan(watched.handle)
            update["generation"] = self._backend.generation(watched.handle)
            # The counts come from the whole file list; only read it again when
            # the index moved on (or was never counted).
            if update["generation"] != known or not counted:
                update.update(_counts(self._backend.files(watched.handle)))
            update["last_scan"] = (
                datetime.now().astimezone().isoformat(timespec="seconds")
            )
        except Exception as error:
            failed = True
            if watched.failed:
                logger.debug(
                    "Rescanning %s still fails: %s", watched.corpus.path, error
                )
            else:
                logger.exception("Rescanning %s failed", watched.corpus.path)
            update = {"available": update["available"]}
        end = self._clock()
        with self._lock:
            watched.failed = failed
            watched.state.update(update)
            watched.state["scanning"] = False
            if watched.poked:
                watched.due = end
            else:
                wait = max(self._interval, self._slow_factor * (end - start))
                watched.due = end + wait

    def state(self, cid: str) -> dict | None:
        """A copy of the corpus's recorded state, or None when it isn't watched."""
        with self._lock:
            watched = self._watched.get(cid)
            return dict(watched.state) if watched else None

    def start(self) -> None:
        """Tick from a daemon thread until ``stop``."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stopped.clear()
        self._thread = threading.Thread(
            target=self._run, name="tilia-library-liveness", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """End the thread; safe to call again, or without ``start``."""
        self._stopped.set()
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(5)

    def _run(self) -> None:
        while not self._stopped.is_set():
            try:
                self.tick()
            except Exception:
                logger.exception("Rescan tick failed")
            self._stopped.wait(_TICK_S)
