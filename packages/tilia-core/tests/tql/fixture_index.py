"""In-memory indexes built from TQL's test fixtures, until the real index exists."""

import re
import sqlite3
from typing import Any

from fake_timemap import FakeTimeMap
from grammars import GRAMMARS

from tilia_core import derived, index_schema, labels

_NOTES = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
_FORM = re.compile(r"Form \((.+)\)$")
_INSERT_COMPONENT = "INSERT INTO components VALUES (?,?,?,?,?,?,?,?,?,?)"


def _spell(name: str) -> tuple[int, int]:
    """(step, accidental) of a pitch name such as "C", "Eb", "F#"."""
    accidental = name[1:].count("#") - name[1:].count("b")
    return _NOTES[name[0].upper()], accidental


class FixtureIndex:
    """An index in memory, and the time maps of its files."""

    def __init__(self, con: sqlite3.Connection, maps: dict[str, FakeTimeMap]) -> None:
        self._con = con
        self._maps = maps

    def connection(self) -> sqlite3.Connection:
        return self._con

    def time_map(self, file_id: str) -> FakeTimeMap | None:
        return self._maps.get(file_id)

    @property
    def generation(self) -> int:
        return 1


def _timeline_role(tl: dict) -> tuple[str | None, str | None]:
    if tl["kind"] == "hierarchy":
        m = _FORM.match(tl["name"])
        if m:
            return "form", m.group(1)
    elif tl["kind"] == "marker" and tl["name"] == "Cadences":
        return "cadences", None
    elif tl["kind"] == "harmony":
        return "harmony", None
    return None, None


class _Builder:
    def __init__(self, con: sqlite3.Connection) -> None:
        self.con = con
        self.maps: dict[str, FakeTimeMap] = {}

    def add_component(
        self,
        cid: str,
        fid: str,
        tid: str,
        kind: str,
        start: float,
        end: float,
        label: str,
        colour: str | None = None,
    ) -> None:
        self.con.execute(
            _INSERT_COMPONENT,
            (
                cid,
                fid,
                tid,
                kind,
                start,
                end,
                label,
                labels.fold(label),
                derived.color(colour),
                "",
            ),
        )

    def add_file(self, k: int, fixture: dict) -> None:
        fid = fixture.get("name", f"f{k}")
        tls = fixture["timelines"]
        beats = [(i, tl) for i, tl in enumerate(tls, 1) if tl["kind"] == "beats"]
        grammar = GRAMMARS[fixture["grammar"]] if "grammar" in fixture else None
        grammar = grammar or labels.WholeLabel()
        tmap = FakeTimeMap.from_fixture(beats[0][1]) if beats else None
        if tmap is not None:
            self.maps[fid] = tmap
        self.con.execute(
            "INSERT INTO files VALUES (?,?,?,?,?)",
            (
                fid,
                fid + ".tla",
                fixture["length"],
                "seconds",
                f"{fid}:t{beats[0][0]}" if beats else None,
            ),
        )
        for ordinal, tl in enumerate(tls, 1):
            tid = f"{fid}:t{ordinal}"
            role, author = _timeline_role(tl)
            kind = "beat" if tl["kind"] == "beats" else tl["kind"]
            self.con.execute(
                "INSERT INTO timelines VALUES (?,?,?,?,?,?,?,?)",
                (
                    tid,
                    fid,
                    kind,
                    tl["name"],
                    labels.fold(tl["name"]),
                    ordinal,
                    role,
                    author,
                ),
            )
            add = getattr(self, "_add_" + tl["kind"])
            add(fid, tid, tl, fixture["length"], grammar)
        if tmap is not None:
            self._add_positions(fid, tmap)
        for name, value in fixture.get("fields", {}).items():
            for item in value if isinstance(value, list) else [value]:
                self.con.execute(
                    "INSERT INTO fields VALUES (?,?,?,?)",
                    ("file", fid, derived.field_name(name), str(item)),
                )

    def _categorise(self, cid: str, label: str, grammar: Any) -> None:
        if label:
            for category in derived.categories(label, grammar):
                self.con.execute("INSERT INTO categories VALUES (?,?)", (cid, category))

    def _add_hierarchy(
        self, fid: str, tid: str, tl: dict, length: float, grammar: Any
    ) -> None:
        rows = []
        for n, unit in enumerate(tl["units"], 1):
            label, level, start, end, *rest = unit
            cid = f"{tid}:c{n}"
            rows.append((cid, level, start, end))
            self.add_component(
                cid, fid, tid, "hierarchy", start, end, label, rest[0] if rest else None
            )
            self._categorise(cid, label, grammar)
        structure = derived.hierarchy_structure(rows)
        for cid, level, _, _ in rows:
            parent, depth = structure[cid]
            self.con.execute(
                "INSERT INTO hierarchies VALUES (?,?,?,?)", (cid, level, parent, depth)
            )

    def _add_marker(
        self, fid: str, tid: str, tl: dict, length: float, grammar: Any
    ) -> None:
        for n, (label, time) in enumerate(tl["units"], 1):
            cid = f"{tid}:c{n}"
            self.add_component(cid, fid, tid, "marker", time, time, label)
            self._categorise(cid, label, grammar)

    def _add_range(
        self, fid: str, tid: str, tl: dict, length: float, grammar: Any
    ) -> None:
        row_ids = {name: f"{tid}:r{i}" for i, name in enumerate(tl["rows"], 1)}
        for n, (row, label, start, end) in enumerate(tl["units"], 1):
            cid = f"{tid}:c{n}"
            self.add_component(cid, fid, tid, "range", start, end, label)
            self.con.execute(
                "INSERT INTO ranges VALUES (?,?,?,?)",
                (cid, row_ids[row], row, labels.fold(row)),
            )
            self._categorise(cid, label, grammar)

    def _add_harmony(
        self, fid: str, tid: str, tl: dict, length: float, grammar: Any
    ) -> None:
        keys = sorted(tl.get("keys", []), key=lambda k: k[0])
        chords = sorted(tl.get("chords", []), key=lambda c: c[0])
        key_ends = derived.implied_spans([k[0] for k in keys], length)
        chord_ends = derived.implied_spans([c[0] for c in chords], length)
        modes = []
        key_ids = []
        for n, ((time, tonic, kind), end) in enumerate(
            zip(keys, key_ends, strict=True), 1
        ):
            step, accidental = _spell(tonic)
            mode = {"step": step, "accidental": accidental, "type": kind}
            cid = f"{tid}:k{n}"
            props = derived.key_fields(mode)
            self.add_component(cid, fid, tid, "key", time, end, props["label"])
            self.con.execute(
                "INSERT INTO keys VALUES (?,?,?,?,?,?)",
                (cid, step, accidental, kind, props["tonic"], props["key"]),
            )
            modes.append(mode)
            key_ids.append(cid)
        in_force = derived.key_in_force([c[0] for c in chords], [k[0] for k in keys])
        for n, (chord, end, k) in enumerate(
            zip(chords, chord_ends, in_force, strict=True), 1
        ):
            time, root, quality, *rest = chord
            step, accidental = _spell(root)
            inversion = rest[0] if rest else 0
            applied_to = rest[1] if len(rest) > 1 else 0
            data = {
                "step": step,
                "accidental": accidental,
                "quality": quality,
                "inversion": inversion,
                "applied_to": applied_to,
            }
            cid = f"{tid}:c{n}"
            props = derived.chord_fields(data, None if k is None else modes[k])
            self.add_component(cid, fid, tid, "chord", time, end, props["label"])
            self.con.execute(
                "INSERT INTO chords VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    cid,
                    step,
                    accidental,
                    quality,
                    inversion,
                    applied_to,
                    None,
                    None if k is None else key_ids[k],
                    props["root"],
                    props["roman"],
                    props["symbol"],
                    props["key"],
                ),
            )

    def _add_beats(
        self, fid: str, tid: str, tl: dict, length: float, grammar: Any
    ) -> None:
        tmap = FakeTimeMap.from_fixture(tl)
        for i, t in enumerate(tmap.beat_times(), 1):
            self.add_component(f"{tid}:c{i}", fid, tid, "beat", t, t, "")

    def _add_positions(self, fid: str, tmap: FakeTimeMap) -> None:
        for count, (start, end, number, label) in enumerate(tmap.measures(), 1):
            self.con.execute(
                "INSERT INTO measures VALUES (?,?,?,?,?,?,?)",
                (fid, count, number, label, start, end, tmap.beats_per_bar),
            )
        rows = self.con.execute(
            'SELECT id, start, "end" FROM components WHERE file_id = ?', (fid,)
        ).fetchall()
        for cid, start, end in rows:
            bar = tmap.bar(start)
            if bar is None:
                continue
            self.con.execute(
                "INSERT INTO positions VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    cid,
                    bar,
                    bar if start == end else tmap.end_bar(end),
                    tmap.beat(start),
                    tmap.pass_of(start),
                    tmap.bar_count(start),
                    tmap.bar_label(start),
                    tmap.measure_beats(start),
                    1 if tmap.is_downbeat(start) else 0,
                ),
            )


def build_index(*fixtures: dict) -> FixtureIndex:
    """An in-memory index of one or more examples.toml fixtures (or dicts of
    the same shape). File k is ``f<k>`` unless the fixture has a ``name``."""
    con = sqlite3.connect(":memory:", check_same_thread=False)
    index_schema.create_schema(con)
    builder = _Builder(con)
    for k, fixture in enumerate(fixtures, 1):
        builder.add_file(k, fixture)
    con.commit()
    return FixtureIndex(con, builder.maps)
