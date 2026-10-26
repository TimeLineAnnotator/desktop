"""The index rows of one file, from its document (research R12).

:func:`rows` gives every table's rows for one document as plain tuples, in the
columns' order, ready for ``executemany``. It reads nothing from disk and takes
no lock: the settings' answers depend only on the timeline and its document, so
a scan builds rows outside the lock. The derived values are WP13's
(:mod:`tilia_core.derived`), and text from the file is stored in NFC
(FR-045).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from tilia_core import derived, labels

from .documents import ComponentDoc, Document, TimelineDoc
from .settings import CorpusSettings
from .time_map import TimeMap

LOG = logging.getLogger(__name__)

Row = tuple[Any, ...]

INDEXED_KINDS = frozenset({"hierarchy", "marker", "range", "harmony", "beat"})
"""The timeline kinds whose components the index holds (FR-005). Every other
kind (score, pdf, audiowave, slider, and kinds the core doesn't know) gives
only its timeline row."""

TIMELINE_COLUMNS = frozenset({"role", "author"})
"""The timeline fields that are columns of ``timelines``, and not also rows of
``fields``."""


@dataclass
class Rows:
    """The rows of one file, by table, each a tuple in the table's columns.

    ``files`` holds the file's one row, with ``path``, ``reason`` and
    ``fingerprint`` left None and ``state`` ``readable``: the scan knows them,
    and :meth:`at` fills them in."""

    file_id: int
    files: list[Row] = field(default_factory=list)
    timelines: list[Row] = field(default_factory=list)
    components: list[Row] = field(default_factory=list)
    hierarchies: list[Row] = field(default_factory=list)
    ranges: list[Row] = field(default_factory=list)
    chords: list[Row] = field(default_factory=list)
    keys: list[Row] = field(default_factory=list)
    categories: list[Row] = field(default_factory=list)
    positions: list[Row] = field(default_factory=list)
    measures: list[Row] = field(default_factory=list)
    fields: list[Row] = field(default_factory=list)

    TABLES = (
        "files",
        "timelines",
        "components",
        "hierarchies",
        "ranges",
        "chords",
        "keys",
        "categories",
        "positions",
        "measures",
        "fields",
    )

    def tables(self) -> dict[str, list[Row]]:
        """Each table's rows, by the table's name."""
        return {name: getattr(self, name) for name in self.TABLES}

    def at(self, path: str, fingerprint: str | None) -> Rows:
        """These rows, with the file's ``path`` and ``fingerprint`` set."""
        (row,) = self.files
        return replace(self, files=[(row[0], path, *row[2:6], fingerprint, *row[7:])])


def roles(document: Document, settings: CorpusSettings) -> dict[str, str | None]:
    """Each timeline's role, by its id in the file: the one the settings set
    (the corpus manifest), else the timeline's own ``role`` field
    (TimeLineAnnotator/project-management#61)."""
    return {
        tl.id: settings.role(tl, document) or _text(tl.fields.get("role"))
        for tl in document.timelines
    }


def rows(
    document: Document,
    settings: CorpusSettings,
    keys: Callable[[], int],
    time_map: TimeMap | None = None,
) -> Rows:
    """Every table's rows for ``document``, with keys from ``keys`` (a callable
    that hands out the next integer key) and the file's time map, if it has
    one."""
    out = Rows(file_id=keys())
    fid = out.file_id
    tl_keys: dict[str, int] = {}
    resolved = roles(document, settings)
    for tl in document.timelines:
        tkey = tl_keys[tl.id] = keys()
        name = labels.nfc(tl.name)
        out.timelines.append(
            (
                tkey,
                fid,
                tl.id,
                tl.kind,
                name,
                labels.fold(name),
                tl.ordinal,
                resolved[tl.id],
                _text(tl.fields.get("author")),
            )
        )
        if tl.kind not in INDEXED_KINDS:
            continue
        _add_fields(out, "timeline", tkey, tl.fields, TIMELINE_COLUMNS)
        _Timeline(out, document, tl, tkey, settings, keys).add()
    _add_fields(out, "file", fid, document.fields)
    map_key: int | None = None
    if time_map is not None:
        map_key = tl_keys.get(time_map.timeline_id)
        if map_key is None:
            LOG.error(
                "the time map names timeline %r, which document %r lacks",
                time_map.timeline_id,
                document.document_id,
            )
        _add_time_map(out, time_map)
    out.files.append(
        (
            fid,
            None,  # path
            document.document_id,
            document.format_version,
            "readable",
            None,  # reason
            None,  # fingerprint
            document.media_length,
            document.time_unit,
            map_key,
            None if map_key is None else int(bool(time_map and time_map.guessed)),
        )
    )
    return out


def _text(value: Any) -> str | None:
    """A single text value from the file, in NFC; None for anything else."""
    return labels.nfc(value) if isinstance(value, str) else None


def _add_fields(
    out: Rows,
    scope: str,
    owner: int,
    fields: Mapping[str, Any],
    skip: frozenset[str] = frozenset(),
) -> None:
    """A row of ``fields`` per value; a list field has one per item."""
    for name, value in fields.items():
        column = derived.field_name(name)
        if column in skip:
            continue
        items = value if isinstance(value, (list, tuple)) else [value]
        for item in items:
            if item is not None:
                out.fields.append((scope, owner, column, labels.nfc(str(item))))


def _lane_order(starts: Sequence[float], names: Sequence[str]) -> list[int]:
    """The order of the points of one lane: by start, then label ignoring case,
    then place in the file. It must agree with TQL's ``lanes.lane_order``,
    which the engine reads lanes in; the tests check the rows against WP13's
    fixture index, built with it."""
    return sorted(
        range(len(starts)), key=lambda i: (starts[i], labels.fold(names[i]), i)
    )


class _Timeline:
    """The rows of one indexed timeline."""

    def __init__(
        self,
        out: Rows,
        document: Document,
        tl: TimelineDoc,
        tkey: int,
        settings: CorpusSettings,
        keys: Callable[[], int],
    ) -> None:
        self.out = out
        self.keys = keys
        self.document = document
        self.tl = tl
        self.tkey = tkey
        self.grammar = settings.grammar(tl, document)

    def add(self) -> None:
        kind = self.tl.kind
        if kind == "harmony":
            self._harmony()
            return
        # a timeline's own kind of component; others aren't indexed
        comps = [c for c in self.tl.components if c.kind == kind]
        if kind == "hierarchy":
            self._hierarchy(comps)
        elif kind == "range":
            self._range(comps)
        else:
            for comp in comps:
                time = float(comp.attrs["time"])
                if kind == "marker":
                    self._component(comp, "marker", time, time, labelled=True)
                else:
                    self._component(comp, "beat", time, time, label="")

    def _component(
        self,
        comp: ComponentDoc,
        kind: str,
        start: float,
        end: float,
        *,
        label: str | None = None,
        labelled: bool = False,
    ) -> int:
        """Add ``comp``'s row of ``components``, its categories when
        ``labelled``, and its fields; return its key."""
        key = self.keys()
        text = (
            labels.nfc(str(comp.attrs.get("label") or "")) if label is None else label
        )
        self.out.components.append(
            (
                key,
                self.out.file_id,
                self.tkey,
                comp.id,
                kind,
                start,
                end,
                text,
                derived.color(comp.attrs.get("color")),
                labels.nfc(str(comp.attrs.get("comments") or "")),
            )
        )
        if labelled and text:
            for category in derived.categories(text, self.grammar):
                self.out.categories.append(
                    (key, category, self.grammar.supertype(category))
                )
        _add_fields(self.out, "component", key, comp.fields)
        return key

    def _hierarchy(self, comps: list[ComponentDoc]) -> None:
        units = []
        keys: dict[str, int] = {}
        for comp in comps:
            start, end = float(comp.attrs["start"]), float(comp.attrs["end"])
            level = comp.attrs.get("level")
            keys[comp.id] = self._component(
                comp, "hierarchy", start, end, labelled=True
            )
            units.append((comp.id, level, start, end))
        structure = derived.hierarchy_structure(units)
        for uid, level, _, _ in units:
            parent, depth = structure[uid]
            self.out.hierarchies.append(
                (keys[uid], level, None if parent is None else keys[parent], depth)
            )

    def _range(self, comps: list[ComponentDoc]) -> None:
        names = {
            r.get("id"): r.get("name") for r in self.tl.attrs.get("rows", []) or []
        }
        for comp in comps:
            start, end = float(comp.attrs["start"]), float(comp.attrs["end"])
            key = self._component(comp, "range", start, end, labelled=True)
            row_id = comp.attrs.get("row_id")
            row = labels.nfc(str(names.get(row_id) or ""))
            self.out.ranges.append((key, row_id, row, labels.fold(row)))

    def _harmony(self) -> None:
        length = self.document.media_length or 0.0
        modes = [c for c in self.tl.components if c.kind == "mode"]
        chords = [c for c in self.tl.components if c.kind == "harmony"]
        # keys in lane order: by time, then label, then place in the file
        key_data = [_mode(c) for c in modes]
        key_labels = [derived.key_fields(m)["label"] for m in key_data]
        order = _lane_order([float(c.attrs["time"]) for c in modes], key_labels)
        modes = [modes[i] for i in order]
        key_data = [key_data[i] for i in order]
        key_starts = [float(c.attrs["time"]) for c in modes]
        key_ends = derived.implied_spans(key_starts, length)
        key_keys: list[int] = []
        for comp, mode, start, end in zip(
            modes, key_data, key_starts, key_ends, strict=True
        ):
            props = derived.key_fields(mode)
            key = self._component(comp, "key", start, end, label=props["label"])
            self.out.keys.append(
                (
                    key,
                    mode["step"],
                    mode["accidental"],
                    mode["type"],
                    props["tonic"],
                    props["key"],
                )
            )
            key_keys.append(key)
        # chords by time, labelled in the key in force, then in lane order
        chords.sort(key=lambda c: float(c.attrs["time"]))
        chord_starts = [float(c.attrs["time"]) for c in chords]
        in_force = derived.key_in_force(chord_starts, key_starts)
        chord_labels = [
            self._chord_props(c, None if k is None else key_data[k])["label"]
            for c, k in zip(chords, in_force, strict=True)
        ]
        order = _lane_order(chord_starts, chord_labels)
        chords = [chords[i] for i in order]
        chord_starts = [chord_starts[i] for i in order]
        in_force = derived.key_in_force(chord_starts, key_starts)
        chord_ends = derived.implied_spans(chord_starts, length)
        for comp, start, end, k in zip(
            chords, chord_starts, chord_ends, in_force, strict=True
        ):
            props = self._chord_props(comp, None if k is None else key_data[k])
            key = self._component(comp, "chord", start, end, label=props["label"])
            custom = comp.attrs.get("custom_text")
            self.out.chords.append(
                (
                    key,
                    comp.attrs.get("step"),
                    comp.attrs.get("accidental"),
                    comp.attrs.get("quality"),
                    comp.attrs.get("inversion"),
                    comp.attrs.get("applied_to"),
                    labels.nfc(custom) if isinstance(custom, str) else None,
                    None if k is None else key_keys[k],
                    props["root"],
                    props["roman"],
                    props["symbol"],
                    props["key"],
                )
            )

    @staticmethod
    def _chord_props(comp: ComponentDoc, mode: dict | None) -> dict:
        a = comp.attrs
        data = {
            "step": a.get("step"),
            "accidental": a.get("accidental"),
            "quality": a.get("quality"),
            "inversion": a.get("inversion") or 0,
            "applied_to": a.get("applied_to") or 0,
            "display_mode": a.get("display_mode"),
            "custom_text": a.get("custom_text"),
        }
        return derived.chord_fields(data, mode)


def _mode(comp: ComponentDoc) -> dict[str, Any]:
    a = comp.attrs
    return {
        "step": a.get("step"),
        "accidental": a.get("accidental"),
        "type": a.get("type"),
    }


def _add_time_map(out: Rows, time_map: TimeMap) -> None:
    """The rows of ``measures``, and of ``positions`` for every unit whose
    start lies on the map (contracts/time-map.md)."""
    for m in time_map.measure_rows():
        out.measures.append(
            (out.file_id, m.count, m.number, m.label, m.start, m.end, m.beats, m.pass_)
        )
    for comp in out.components:
        key, start, end = comp[0], comp[5], comp[6]
        p = time_map.positions(start, end)
        if p is None:
            continue
        out.positions.append(
            (
                key,
                p.bar,
                p.end_bar,
                p.beat,
                p.pass_,
                p.bar_count,
                p.bar_label,
                p.bar_beat_count,
                int(p.downbeat),
            )
        )
