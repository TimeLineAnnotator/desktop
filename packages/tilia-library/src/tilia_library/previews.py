"""Previews kept between preview and apply.

A bulk edit is previewed first; the server keeps the plan it showed, so that
on apply it can plan again from the files as they are now and check that the
writes the user ticked are the ones they saw.
"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable, Collection
from dataclasses import dataclass

PREVIEW_TTL_S = 3600.0


@dataclass
class Preview:
    """One preview: the statement, the plan shown for it, and where it was shown."""

    id: str
    cid: str
    tab: str
    statement: str
    answer: dict
    created: float


class Previews:
    """The previews of this run, at most one per (corpus, tab), each with a TTL."""

    def __init__(
        self,
        *,
        ttl: float = PREVIEW_TTL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._by_id: dict[str, Preview] = {}
        self._by_tab: dict[tuple[str, str], str] = {}

    def add(self, cid: str, tab: str, statement: str, answer: dict) -> Preview:
        """Keep a preview, replacing the older one of the same corpus and tab.

        Every expired preview is dropped first, so those of closed tabs don't pile up.
        """
        now = self._clock()
        preview = Preview(secrets.token_urlsafe(16), cid, tab, statement, answer, now)
        with self._lock:
            for old in [p for p in self._by_id.values() if self._expired(p, now)]:
                self._drop(old)
            older = self._by_tab.get((cid, tab))
            if older is not None:
                self._by_id.pop(older, None)
            self._by_id[preview.id] = preview
            self._by_tab[(cid, tab)] = preview.id
        return preview

    def get(self, preview_id: str) -> Preview | None:
        """The preview, or None when unknown or older than the TTL (it is dropped)."""
        with self._lock:
            preview = self._by_id.get(preview_id)
            if preview is None:
                return None
            if self._expired(preview, self._clock()):
                self._drop(preview)
                return None
            return preview

    def discard(self, preview_id: str) -> None:
        """Forget the preview; an unknown one is ignored."""
        with self._lock:
            preview = self._by_id.get(preview_id)
            if preview is not None:
                self._drop(preview)

    def __len__(self) -> int:
        with self._lock:
            return len(self._by_id)

    def __bool__(self) -> bool:
        # an empty store is still a store: callers write `previews or Previews()`
        return True

    def _expired(self, preview: Preview, now: float) -> bool:
        return now - preview.created > self._ttl

    def _drop(self, preview: Preview) -> None:
        del self._by_id[preview.id]
        if self._by_tab.get((preview.cid, preview.tab)) == preview.id:
            del self._by_tab[(preview.cid, preview.tab)]


def writes_by_key(answer: dict) -> dict[str, list[dict]]:
    """The writes of each plan entry, by the entry's key."""
    return {entry["key"]: entry["writes"] for entry in answer["plan"]}


def same_writes(old: dict, new: dict, keys: Collection[str]) -> bool:
    """Whether both plans have the same writes, in order, for every given key."""
    before = writes_by_key(old)
    after = writes_by_key(new)
    return all(
        key in before and key in after and before[key] == after[key] for key in keys
    )
