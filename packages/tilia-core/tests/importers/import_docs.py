"""Builds `tla.Document`s for the importers' tests.

Beat timelines come from `docs.beat_timeline` (tests/timemap/docs.py), which
builds their measure table as WP3's reader does; there is no second one here.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from tilia_core import tla


def document(
    *,
    media_length: float | None = 60.0,
    timelines: Iterable[tla.Timeline] = (),
    time_unit: str = "seconds",
) -> tla.Document:
    return tla.Document(
        document_id=tla.new_id(),
        format_version=tla.FORMAT_VERSION,
        time_unit=time_unit,
        media_length=media_length,
        timelines={timeline.id: timeline for timeline in timelines},
    )


def timeline(
    kind: str,
    *,
    name: str = "",
    ordinal: int = 1,
    components: Iterable[tla.Component] = (),
    attrs: dict[str, Any] | None = None,
) -> tla.Timeline:
    return tla.Timeline(
        id=tla.new_id(),
        kind=kind,
        ordinal=ordinal,
        name=name,
        attrs={} if attrs is None else attrs,
        components={component.id: component for component in components},
    )


def component(kind: str, **attrs: Any) -> tla.Component:
    return tla.Component(id=tla.new_id(), kind=kind, attrs=attrs)
