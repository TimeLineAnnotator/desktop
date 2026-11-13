"""The index kept on disk between runs, so that opening a corpus again reads
only the files that changed (TimeLineAnnotator/project-management#125,
revisited for the CLI's ``tilia query``).

- **Where:** one file per corpus folder, in the per-user cache folder
  (:func:`folder`): ``~/Library/Caches/TiLiA/library/indexes`` on macOS,
  ``~/.cache/TiLiA/library/indexes`` on Linux and
  ``%LOCALAPPDATA%\\TiLiA\\TiLiA\\Cache\\library\\indexes`` on Windows; never in
  the corpus folder, so a network or cloud-synced corpus holds no database.
  The environment variable :data:`ENV` names another folder, or ``off``.
- **What:** a SQLite copy of the index (``Connection.backup``), plus two tables
  of plain data, JSON: each file's record, and its time map. No pickle.
- **When:** written when a corpus was opened and something changed, and when
  it is closed after a change. A copy is written to a temporary file and
  renamed over the last one, so a reader sees a whole copy or none. It is read
  once, when the corpus opens, and never held open.
- **Which:** only the indexes of the default reader, settings and time maps
  (:func:`applies`): what any other reader or settings would give isn't known
  from the files alone. A copy written by other code (:func:`stamp`: the
  core's sources and versions) or for another folder is thrown away.

Opening from a copy is a rescan: files whose size and date are as the copy
saw them aren't read; the others are, as a scan reads them. A file that has
gone since is forgotten, as a first build wouldn't know it. Deleting a copy
only costs the time of a first build.
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib.metadata
import json
import logging
import os
import secrets
import sqlite3
import sys
import threading
import zlib
from collections.abc import Mapping
from fractions import Fraction
from functools import cache as _once
from pathlib import Path
from typing import Any

import platformdirs

from tilia_core import state
from tilia_core.timemap.table import FrozenMetadata, MeasureRow
from tilia_core.timemap.timemap import TimeMap as Wp9TimeMap
from tilia_core.timemap.units import MeasureMeter

from .documents import DocumentReader
from .scan import FileRecord, Scanner, ScanReport, shared_ids
from .settings import CorpusSettings, NoSettings
from .time_map import Measure, Positions, TimeMap, TimeMapOf
from .tla_reader import TlaReader
from .tla_reader import find_time_map as wp9_find_time_map

LOG = logging.getLogger(__name__)

VERSION = 1
"""The layout of a copy. A change to it, or to anything the copy holds, must
change :func:`stamp`; the sources do, so this only needs a bump for a change
the sources don't show."""

ENV = "TILIA_INDEX_CACHE"
"""An environment variable: the folder to keep copies in, instead of
:func:`folder`'s; ``off`` (or empty) keeps none."""

_META = "tilia_cache_meta"
_FILES = "tilia_cache_files"
_OFF = ("", "0", "off", "no", "false")


def folder() -> Path | None:
    """The folder the copies are kept in; None when :data:`ENV` turns them
    off."""
    given = os.environ.get(ENV)
    if given is not None:
        return None if given.strip().lower() in _OFF else Path(given)
    cache = platformdirs.user_cache_dir(state.APP_NAME, state.APP_AUTHOR)
    return Path(cache) / state.FOLDER / "indexes"


def path_for(root: Path) -> Path | None:
    """Where the copy of the corpus at ``root`` (resolved) is kept; None when
    copies are off."""
    where = folder()
    if where is None:
        return None
    name = hashlib.sha256(os.fsencode(root)).hexdigest()[:32]
    return where / f"{name}.sqlite"


def applies(
    reader: DocumentReader, settings: CorpusSettings, time_map_of: TimeMapOf
) -> bool:
    """Whether an index read with these can be kept: only with the defaults,
    whose rows depend on nothing but the files and the core's code."""
    return (
        type(reader) is TlaReader
        and type(settings) is NoSettings
        and time_map_of is wp9_find_time_map
    )


def _version(dist: str) -> str:
    try:
        return importlib.metadata.version(dist)
    except importlib.metadata.PackageNotFoundError:
        return "-"


@_once
def stamp() -> str:
    """What a copy must have been written by: this layout, the core's sources
    (or, in a build without them, its version), and the versions of what reads
    harmonies. A copy with another stamp is thrown away."""
    digest = hashlib.sha256(f"{VERSION}\n{sys.version_info[:2]}\n".encode())
    root = Path(__file__).resolve().parents[1]  # tilia_core
    sources = sorted(root.rglob("*.py"))
    for source in sources:
        digest.update(source.relative_to(root).as_posix().encode() + b"\0")
        digest.update(source.read_bytes())
    for dist in ("tilia-core", "music21"):
        digest.update(f"{dist}={_version(dist)}\n".encode())
    return digest.hexdigest()


# --------------------------------------------------------------------------- #
# Time maps as plain data
# --------------------------------------------------------------------------- #
_CLASSES: dict[str, type] = {
    cls.__name__: cls for cls in (Wp9TimeMap, MeasureRow, MeasureMeter)
}
# each class's fields that its constructor takes, in order
_FIELDS: dict[type, tuple[str, ...]] = {
    cls: tuple(f.name for f in dataclasses.fields(cls) if f.init)
    for cls in _CLASSES.values()
}
_SCALARS = frozenset({type(None), bool, int, float, str})


def _plain(value: Any) -> Any:
    """``value`` as JSON can hold it, tagged where JSON alone would lose its
    type: tuples, fractions, a measure's metadata and the time map's
    dataclasses (the values their constructors take, in order). By exact
    type first: a big time map holds hundreds of thousands of values."""
    kind = type(value)
    if kind in _SCALARS:
        return value
    if kind is tuple:
        return {"T": [v if type(v) in _SCALARS else _plain(v) for v in value]}
    if kind is MeasureMeter:  # most measures share their meter with others
        known = _meters.get(value)
        if known is None:
            known = _meters[value] = _fields_plain(value, _FIELDS[kind])
        return known
    names = _FIELDS.get(kind)
    if names is not None:
        return _fields_plain(value, names)
    if kind is Fraction:
        return {"F": [value.numerator, value.denominator]}
    if kind is FrozenMetadata:
        return {"M": {key: _plain(item) for key, item in value.items()}}
    if kind is list:
        return [_plain(item) for item in value]
    if isinstance(value, (int, float, str)):  # a subclass, such as an enum
        return value
    raise TypeError(f"a time map can't hold {kind.__name__}")


_meters: dict[MeasureMeter, dict[str, Any]] = {}


def _fields_plain(value: Any, names: tuple[str, ...]) -> dict[str, Any]:
    return {"C": type(value).__name__, "v": [_plain(getattr(value, n)) for n in names]}


def _unplain(value: Any) -> Any:
    """What :func:`_plain` gave, back."""
    if type(value) is list:
        return [_unplain(item) for item in value]
    if type(value) is not dict:
        return value
    if "T" in value:
        return tuple(_unplain(item) for item in value["T"])
    if "C" in value:
        cls = _CLASSES[value["C"]]
        names = _FIELDS[cls]
        values = value["v"]
        if len(values) != len(names):
            raise ValueError(f"{cls.__name__} with {len(values)} values")
        return cls(**{n: _unplain(v) for n, v in zip(names, values, strict=True)})
    if "F" in value:
        numerator, denominator = value["F"]
        return Fraction(numerator, denominator)
    if "M" in value:
        return FrozenMetadata({k: _unplain(v) for k, v in value["M"].items()})
    raise ValueError(f"not a value of a time map: {value!r}")


def time_map_data(time_map: TimeMap) -> bytes:
    """``time_map`` as JSON, compressed: its measures look much alike.
    Raises ``TypeError`` for a time map that isn't WP9's."""
    if isinstance(time_map, LazyTimeMap):
        return time_map.data
    if type(time_map) is not Wp9TimeMap:
        raise TypeError(f"not WP9's time map: {type(time_map).__name__}")
    try:
        text = json.dumps(_plain(time_map), separators=(",", ":"))
    finally:
        _meters.clear()
    return zlib.compress(text.encode("ascii"), 1)


def time_map_from(data: bytes) -> Wp9TimeMap:
    """The time map that :func:`time_map_data` gave ``data`` for."""
    try:
        text = zlib.decompress(data)
    except zlib.error as err:
        raise ValueError(f"not a time map: {err}") from err
    found = _unplain(json.loads(text))
    if not isinstance(found, Wp9TimeMap):
        raise ValueError("not a time map")
    return found


class LazyTimeMap:
    """A time map read back from a copy, built from its JSON when first used:
    a corpus opens without building the time maps no query asks for. A worker
    process that builds a file's rows sends its time map back as one, too
    (:class:`~.scan.Prebuilt`): it pickles as its JSON."""

    def __init__(self, timeline_id: str, guessed: bool, data: bytes) -> None:
        self.timeline_id = timeline_id
        self.guessed = guessed
        self.data = data
        self._map: Wp9TimeMap | None = None
        self._lock = threading.Lock()

    def __reduce__(self) -> tuple[type[LazyTimeMap], tuple[str, bool, bytes]]:
        return (LazyTimeMap, (self.timeline_id, self.guessed, self.data))

    def built(self) -> Wp9TimeMap:
        """The time map itself."""
        if self._map is None:
            with self._lock:
                if self._map is None:
                    self._map = time_map_from(self.data)
        return self._map

    def measures(self) -> list[tuple[float, float, int, str]]:
        return self.built().measures()

    def measure_rows(self) -> list[Measure]:
        return self.built().measure_rows()

    def positions(self, start: float, end: float) -> Positions | None:
        return self.built().positions(start, end)

    def position(self, t: float, unit: str = "bar") -> float | None:
        return self.built().position(t, unit)

    def length(self, start: float, end: float, unit: str = "bar") -> float | None:
        return self.built().length(start, end, unit)

    def unit_seconds(self, t: float, unit: str) -> float | None:
        return self.built().unit_seconds(t, unit)

    def __getattr__(self, name: str) -> Any:
        # anything else WP9's time map offers; never this object's own fields
        if name.startswith("__") or name in ("_map", "_lock", "data"):
            raise AttributeError(name)
        return getattr(self.built(), name)


# --------------------------------------------------------------------------- #
# Records as plain data
# --------------------------------------------------------------------------- #
_RECORD_FIELDS = tuple(
    f.name
    for f in dataclasses.fields(FileRecord)
    if f.name not in ("native", "time_map", "keys")
)


def _record_text(record: FileRecord, root: Path) -> str:
    data: dict[str, Any] = {name: getattr(record, name) for name in _RECORD_FIELDS}
    data["keys"] = list(record.keys)
    try:
        data["native"] = list(record.native.relative_to(root).parts)
    except ValueError:  # never, as the walk finds every file below the root
        data["native"] = None
        data["native_path"] = os.fspath(record.native)
    return json.dumps(data, separators=(",", ":"))


def _record_from(
    text: str,
    time_map: bytes | None,
    timeline_id: str | None,
    guessed: bool,
    root: Path,
) -> FileRecord:
    data = json.loads(text)
    parts = data.pop("native")
    native_path = data.pop("native_path", None)
    native = root.joinpath(*parts) if parts is not None else Path(native_path)
    keys = tuple(int(key) for key in data.pop("keys"))
    tmap = None
    if time_map is not None:
        if timeline_id is None:
            raise ValueError("a time map without its timeline")
        tmap = LazyTimeMap(timeline_id, bool(guessed), time_map)
    return FileRecord(native=native, keys=keys, time_map=tmap, **data)


# --------------------------------------------------------------------------- #
# Writing and reading a copy
# --------------------------------------------------------------------------- #
class _Stale(Exception):
    """A copy written by other code, or for another folder."""


def _remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as err:
        LOG.warning("the old copy of an index at %s can't be removed: %s", path, err)


def save(scanner: Scanner, path: Path) -> int | None:
    """Write the index of ``scanner``'s corpus, with its records, to
    ``path``; the generation written, None when it couldn't be (which is
    logged: the corpus works on without a copy)."""
    tmp = path.with_name(f"{path.name}.{secrets.token_hex(4)}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with scanner.turn:  # no scan changes the records meanwhile
            records = dict(scanner.records)
            files = [
                (
                    p,
                    _record_text(rec, scanner.root),
                    None if tmap is None else time_map_data(tmap),
                    None if tmap is None else tmap.timeline_id,
                    None if tmap is None else int(tmap.guessed),
                )
                for p, rec in sorted(records.items())
                for tmap in [rec.time_map]
            ]
            meta = {
                "stamp": stamp(),
                "root": os.fspath(scanner.root),
                "next_key": str(scanner.next_key),
                "unlisted": json.dumps(list(scanner.store.unlisted)),
            }
            con = sqlite3.connect(tmp, isolation_level=None)
            try:
                generation = scanner.store.save_to(con)
                con.execute(
                    f"CREATE TABLE {_META} (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                con.execute(
                    f"CREATE TABLE {_FILES} "
                    "(path TEXT PRIMARY KEY, record TEXT NOT NULL, "
                    "time_map BLOB, timeline_id TEXT, guessed INTEGER)"
                )
                con.execute("BEGIN")
                con.executemany(f"INSERT INTO {_META} VALUES (?, ?)", meta.items())
                con.executemany(f"INSERT INTO {_FILES} VALUES (?, ?, ?, ?, ?)", files)
                con.execute("COMMIT")
            finally:
                con.close()
        state._replace_with_retry(tmp, path)
        return generation
    except (OSError, sqlite3.Error, TypeError, ValueError) as err:
        LOG.warning(
            "the index of %s can't be kept on disk at %s: %s", scanner.root, path, err
        )
        _remove(tmp)
        return None


def load(scanner: Scanner, path: Path) -> bool:
    """Fill ``scanner``'s empty index and records from the copy at ``path``;
    whether there was one it could use. A copy it can't use is removed. After
    a failure, the store may hold part of the copy: throw it away."""
    if not path.is_file():
        return False
    try:
        con = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
        try:
            meta = dict(con.execute(f"SELECT key, value FROM {_META}"))
            if meta.get("stamp") != stamp() or meta.get("root") != os.fspath(
                scanner.root
            ):
                raise _Stale
            records: dict[str, FileRecord] = {}
            maps: dict[int, TimeMap] = {}
            rows = con.execute(
                f"SELECT path, record, time_map, timeline_id, guessed FROM {_FILES}"
            )
            for p, text, time_map, timeline_id, guessed in rows:
                record = _record_from(
                    text, time_map, timeline_id, guessed, scanner.root
                )
                records[p] = record
                if record.time_map is not None:
                    maps[record.key] = record.time_map
            next_key = int(meta["next_key"])
            unlisted = tuple(json.loads(meta["unlisted"]))
            scanner.store.load_from(con, maps, drop=(_META, _FILES))
        finally:
            con.close()
    except _Stale:
        LOG.info("the copy of the index at %s is out of date; reading the files", path)
        _remove(path)
        return False
    except (sqlite3.Error, KeyError, ValueError, TypeError) as err:
        LOG.warning(
            "the copy of the index at %s can't be used (%s); reading the files",
            path,
            err,
        )
        _remove(path)
        return False
    scanner.store.unlisted = unlisted
    scanner.restore(records, next_key)
    return True


def reopen(scanner: Scanner, path: Path) -> ScanReport | None:
    """Open the corpus from its copy at ``path`` and rescan it: the report a
    first build would have given, None without a usable copy. Files gone since
    are forgotten, as a first build wouldn't know them."""
    if not load(scanner, path):
        return None
    scan = scanner.scan()
    gone = [p for p, rec in scanner.records.items() if rec.state == "unavailable"]
    if gone and scan.error is None:
        scanner.forget(gone)
    return _as_built(scanner.records, scanner.store.generation, scan.error)


def _as_built(
    records: Mapping[str, FileRecord], generation: int, error: str | None
) -> ScanReport:
    """The report of a first build that found ``records``."""
    return ScanReport(
        added=tuple(sorted(records)),
        changed=(),
        moved=(),
        unavailable=(),
        back=(),
        unreadable=tuple(
            (p, rec.line, rec.reason or "")
            for p, rec in sorted(records.items())
            if rec.state == "unreadable"
        ),
        shared_ids=tuple(shared_ids(dict(records))),
        generation_before=0,
        generation_after=generation,
        error=error,
    )
