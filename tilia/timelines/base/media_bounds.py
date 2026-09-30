from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import tilia.constants
from tilia.requests import Get, get

_restoring_depth = 0


@contextmanager
def restoring_components() -> Iterator[None]:
    """
    Lets components rebuilt from saved or recorded state end up to
    DURATION_JITTER_TOLERANCE past the media duration.

    Opening a file loads its media in "keep" mode (#453): when the player
    reports a slightly shorter duration (YouTube does so asynchronously),
    only the duration is updated and components at the old end are left
    past it. States saved or recorded afterwards contain those components,
    and rebuilding them must neither clamp nor drop them, as a later report
    may bring the original duration back. Components created otherwise are
    still bound by the media duration itself.
    """
    global _restoring_depth
    _restoring_depth += 1
    try:
        yield
    finally:
        _restoring_depth -= 1


def is_past_media_end(time: float) -> bool:
    limit = get(Get.MEDIA_DURATION)
    if _restoring_depth:
        limit += tilia.constants.DURATION_JITTER_TOLERANCE
    return time > limit
