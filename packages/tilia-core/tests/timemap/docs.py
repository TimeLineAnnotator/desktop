"""Builds `tla.Document`s for the time map's tests, with the measure table as WP3's reader builds it."""

from __future__ import annotations

from typing import Any

from tilia_core import tla


def beat_timeline(
    beats: list[dict[str, Any]],
    *,
    id: str | None = None,
    ordinal: int = 1,
    role: str | None = None,
    measure_source: str = "tapped",
) -> tla.Timeline:
    """A beat timeline from dicts `{"time", "measure", "beat_unit"}`; the last two are optional."""
    components: dict[str, tla.Component] = {}
    for beat in beats:
        attrs: dict[str, Any] = {"time": beat["time"]}
        for key in ("measure", "beat_unit"):
            if beat.get(key) is not None:
                attrs[key] = beat[key]
        component_id = tla.new_id()
        components[component_id] = tla.Component(
            id=component_id, kind="BEAT", attrs=attrs
        )
    metadata: tla.Metadata = {} if role is None else {"role": role}
    return tla.Timeline(
        id=id or tla.new_id(),
        kind="beat",
        ordinal=ordinal,
        metadata=metadata,
        attrs={"measure_source": measure_source},
        measures=_table(components, measure_source),
        components=components,
    )


def _table(components: dict[str, tla.Component], source: str) -> tla.MeasureTable:
    rows: list[tla.Measure] = []
    for component in components.values():
        mark = component.attrs.get("measure")
        if mark is not None:
            rows.append(_row(component.id, mark, rows, source))
        if rows:
            rows[-1].beats.append(component.id)
    return tla.MeasureTable(source=source, rows=rows)


def _row(
    downbeat: str, mark: dict[str, Any], rows: list[tla.Measure], source: str
) -> tla.Measure:
    number = (
        mark["number"] if "number" in mark else (rows[-1].number + 1 if rows else 1)
    )
    return tla.Measure(
        id=downbeat,
        number=number,
        label=mark.get("label", str(number)),
        beats=[],
        beat_unit=tla.BeatUnit(denominator=4, units="1", assumed=True),
        source=mark.get("source", source),
        force_display=bool(mark.get("force_display", False)),
        cadenza=bool(mark.get("cadenza", False)),
        restart=bool(mark.get("restart", False)),
        next=mark.get("next"),
        metadata=mark.get("metadata", {}),
    )


def document(
    *timelines: tla.Timeline,
    media_length: float | None = None,
    time_unit: str = "seconds",
) -> tla.Document:
    return tla.Document(
        document_id=tla.new_id(),
        format_version="2.0",
        time_unit=time_unit,
        media_length=media_length,
        timelines={timeline.id: timeline for timeline in timelines},
    )
