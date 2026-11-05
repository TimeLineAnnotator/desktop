"""Builds `tla.Document`s for the time map's tests.

Each measure table is made from the beats in the order given: a beat with a
mark starts a row, and each beat joins the last row, even one without a time.
The reader's table (`tla.measures_of`) differs: it sorts the beats by time, and
leaves out those without one, so these tests can give the time map what no
file read gives it. Like the reader's, it leaves out every tap marked closing.
"""

from __future__ import annotations

from typing import Any

from tilia_core import tla

# The format requires a beat timeline's height, and has no default for it: TiLiA's
# comes from each user's settings. This is TiLiA's own default.
BEAT_TIMELINE_HEIGHT = 35


def beat_timeline(
    beats: list[dict[str, Any]],
    *,
    id: str | None = None,
    ordinal: int = 1,
    role: str | None = None,
    measure_source: str = "tapped",
) -> tla.Timeline:
    """A beat timeline from dicts `{"time", "measure", "beat_unit", "closing"}`;
    the last three are optional."""
    components: dict[str, tla.Component] = {}
    for beat in beats:
        attrs: dict[str, Any] = {"time": beat["time"]}
        for key in ("measure", "beat_unit", "closing"):
            if beat.get(key) is not None:
                attrs[key] = beat[key]
        component_id = tla.new_id()
        components[component_id] = tla.Component(
            id=component_id, kind="beat", attrs=attrs
        )
    metadata: tla.Metadata = {} if role is None else {"role": role}
    return tla.Timeline(
        id=id or tla.new_id(),
        kind="beat",
        ordinal=ordinal,
        metadata=metadata,
        attrs={"height": BEAT_TIMELINE_HEIGHT, "measure_source": measure_source},
        measures=_table(components, measure_source),
        components=components,
    )


def _table(components: dict[str, tla.Component], source: str) -> tla.MeasureTable:
    rows: list[tla.Measure] = []
    for component in components.values():
        if component.attrs.get("closing"):
            continue
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


def pickup_piece() -> tla.Timeline:
    """4/4 with a one-beat pickup, ending on a three-beat bar: bars 0-5, a beat
    every second from 1 s, the last at 20 s."""
    marks = {1: {"number": 0}, 2: {}, 6: {}, 10: {}, 14: {}, 18: {}}
    return beat_timeline(
        [{"time": float(t), "measure": marks.get(t)} for t in range(1, 21)]
    )


def closed_piece(closing: float = 6.0, **tap: Any) -> tla.Timeline:
    """Two bars of two beats, a beat every second from 1 s, and a closing tap."""
    return beat_timeline(
        [
            {"time": 1.0, "measure": {"number": 1}},
            {"time": 2.0},
            {"time": 3.0, "measure": {}},
            {"time": 4.0},
            {"time": closing, "closing": True, **tap},
        ]
    )


def two_movements(closed: bool = False) -> tla.Timeline:
    """Bars 1 and 2, a beat every second from 1 s, with a closing tap at 5.5;
    then, after a pause, bars 1 and 2 of a second movement, from 8 s. With
    `closed`, the second has a closing tap too, at 13.0."""
    beats: list[dict[str, Any]] = [
        {"time": 1.0, "measure": {"number": 1}},
        {"time": 2.0},
        {"time": 3.0, "measure": {}},
        {"time": 4.0},
        {"time": 5.5, "closing": True},
        {"time": 8.0, "measure": {"number": 1, "restart": True}},
        {"time": 9.0},
        {"time": 10.0, "measure": {}},
        {"time": 11.0},
    ]
    if closed:
        beats.append({"time": 13.0, "closing": True})
    return beat_timeline(beats)


def read_as_a_file(*timelines: tla.Timeline, **kwargs: Any) -> tla.Document:
    """A document written to bytes and read back, as the core reads a file, so
    that the measure table is the reader's."""
    return tla.loads(tla.canonical_bytes(document(*timelines, **kwargs)))
