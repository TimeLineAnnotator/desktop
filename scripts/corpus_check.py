"""Check the corpus index on a real folder, by hand (TimeLineAnnotator/project-management#155).

    uv run --package tilia-core python scripts/corpus_check.py FOLDER
    uv run --package tilia-core python scripts/corpus_check.py --rescan-check FOLDER

The first form opens FOLDER as a corpus and prints:

- the files by state, with each unreadable file's path, line and reason, and
  whether WP3's reader gives that reason on its own;
- the timelines and the units of each kind TQL searches, as ``tilia_core.tla``
  reads them from the files beside those in the index, and the files where they
  differ (SC-001);
- the build's time and the times of rescans that find nothing (SC-004);
- whether every file of the corpus has the same SHA-256 before and after, and
  whether every file under the folder has the same size and modification time
  (SC-005).

``--rescan-check`` copies FOLDER to a temporary folder and indexes the copy. It
applies User Story 2's changes to the copy (a rename, a move into a subfolder,
a deletion, a touch, line endings changed, one label changed through the
core's writer and one by rewriting the file's text), rescans, builds a fresh
index of the copy, and compares the two (SC-002). Only the copy is changed.

The script is not part of CI: the corpora it is for are private, or their
licences keep them out of it. It uses the standard library and the core only.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import shutil
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from tilia_core import open_corpus, tla
from tilia_core.corpus import Corpus, ScanReport
from tilia_core.corpus.build import INDEXED_KINDS
from tilia_core.corpus.documents import UnreadableFile

LOG = logging.getLogger(__name__)

RESCANS = 3
"""How many no-change rescans are timed."""

EDIT = " (edited by corpus_check)"
"""What the two edits of ``--rescan-check`` add to a label."""

# The units the index holds, by the kind of the timeline and of the component
# in the file: a harmony timeline's chords and keys, and every other indexed
# timeline's own kind of component.
UNIT_KINDS = {("harmony", "harmony"): "chord", ("harmony", "mode"): "key"}
UNIT_KINDS.update({(k, k): k for k in INDEXED_KINDS if k != "harmony"})

# Every table of the index, with each key written as the (path, uuid) of what
# it names, so that two indexes of one folder can be compared row by row.
DUMP = {
    "files": "SELECT path, document_id, format_version, state, reason, fingerprint, "
    "media_length, time_unit, (SELECT uuid FROM timelines t WHERE t.id = f.time_map), "
    "time_map_guessed FROM files f",
    "timelines": "SELECT f.path, t.uuid, t.kind, t.name, t.name_folded, t.ordinal, "
    "t.role, t.author FROM timelines t JOIN files f ON f.id = t.file_id",
    "components": 'SELECT f.path, t.uuid, c.uuid, c.kind, c.start, c."end", c.label, '
    "c.color, c.comments FROM components c JOIN files f ON f.id = c.file_id "
    "JOIN timelines t ON t.id = c.timeline_id",
    "hierarchies": "SELECT f.path, c.uuid, h.level, p.uuid, h.depth FROM hierarchies h "
    "JOIN components c ON c.id = h.component_id JOIN files f ON f.id = c.file_id "
    "LEFT JOIN components p ON p.id = h.parent_id",
    "ranges": "SELECT f.path, c.uuid, r.row_id, r.row, r.row_folded FROM ranges r "
    "JOIN components c ON c.id = r.component_id JOIN files f ON f.id = c.file_id",
    "chords": "SELECT f.path, c.uuid, x.step, x.accidental, x.quality, x.inversion, "
    "x.applied_to, x.custom_text, k.uuid, x.root, x.roman, x.symbol, x.key "
    "FROM chords x JOIN components c ON c.id = x.component_id "
    "JOIN files f ON f.id = c.file_id LEFT JOIN components k ON k.id = x.key_id",
    "keys": "SELECT f.path, c.uuid, k.step, k.accidental, k.mode, k.tonic, k.key "
    "FROM keys k JOIN components c ON c.id = k.component_id "
    "JOIN files f ON f.id = c.file_id",
    "categories": "SELECT f.path, c.uuid, x.category, x.supertype FROM categories x "
    "JOIN components c ON c.id = x.component_id JOIN files f ON f.id = c.file_id",
    "positions": "SELECT f.path, c.uuid, p.bar, p.end_bar, p.beat, p.pass, "
    "p.bar_count, p.bar_label, p.bar_beat_count, p.downbeat FROM positions p "
    "JOIN components c ON c.id = p.component_id JOIN files f ON f.id = c.file_id",
    "measures": 'SELECT f.path, m.count, m.number, m.label, m.start, m."end", '
    "m.beats, m.pass FROM measures m JOIN files f ON f.id = m.file_id",
    "fields": "SELECT x.scope, CASE x.scope "
    "WHEN 'file' THEN (SELECT path FROM files WHERE id = x.owner_id) "
    "WHEN 'timeline' THEN (SELECT f.path || ':' || t.uuid FROM timelines t "
    "JOIN files f ON f.id = t.file_id WHERE t.id = x.owner_id) "
    "ELSE (SELECT f.path || ':' || c.uuid FROM components c "
    "JOIN files f ON f.id = c.file_id WHERE c.id = x.owner_id) END, "
    "x.name, x.value FROM fields x",
}

Counts = tuple[int, Counter[str]]
"""A file's timelines, and its units by kind."""


# --------------------------------------------------------------------------- #
# The folder, before and after
# --------------------------------------------------------------------------- #
def _hidden(rel: Path) -> bool:
    return any(part.startswith(".") for part in rel.parts)


def listing(folder: Path) -> dict[str, tuple[int, int]]:
    """Every file under ``folder``, by relative path, with its size and
    modification time, hidden folders included."""
    out: dict[str, tuple[int, int]] = {}
    for root, _, names in os.walk(folder):
        for name in names:
            path = Path(root, name)
            try:
                info = path.stat()
            except OSError as err:
                LOG.warning("can't look at %s: %s", path, err)
                continue
            out[path.relative_to(folder).as_posix()] = (info.st_size, info.st_mtime_ns)
    return out


def checksums(folder: Path, files: Iterable[str]) -> dict[str, str]:
    """The SHA-256 of each of ``files``, relative to ``folder``, that is a
    ``.tla`` file outside hidden folders: the files the corpus reads."""
    out = {}
    for rel in files:
        if rel.lower().endswith(".tla") and not _hidden(Path(rel)):
            out[rel] = hashlib.sha256((folder / rel).read_bytes()).hexdigest()
    return out


# --------------------------------------------------------------------------- #
# What the files hold, read on their own
# --------------------------------------------------------------------------- #
def _kind(kind: object) -> str:
    return kind.spelling if isinstance(kind, tla.UnknownKind) else str(kind)


def counts_in_file(doc: tla.Document) -> Counts:
    """The timelines of ``doc`` and its units of each kind TQL searches."""
    units: Counter[str] = Counter()
    for tl in doc.timelines.values():
        tl_kind = _kind(tl.kind)
        for comp in tl.components.values():
            unit = UNIT_KINDS.get((tl_kind, _kind(comp.kind)))
            if unit is not None:
                units[unit] += 1
    return len(doc.timelines), units


def reader_reason(path: Path) -> str | None:
    """The reason ``tla`` gives on its own for not reading ``path``, as the
    index words it; None when it reads it."""
    try:
        tla.read(path)
    except tla.UnreadableFile as err:
        return str(UnreadableFile(path, err.message, err.line))
    except OSError as err:
        return f"can't read: {err.strerror or err}"
    return None


def counts_in_index(corpus: Corpus) -> dict[str, Counts]:
    """The timelines and units of each kind the index holds, by file."""
    out: dict[str, Counts] = {}
    with corpus.reading() as r:
        con = r.connection
        for path, n in con.execute(
            "SELECT f.path, count(t.id) FROM files f "
            "LEFT JOIN timelines t ON t.file_id = f.id "
            "WHERE f.state = 'readable' GROUP BY f.id"
        ):
            out[path] = (n, Counter())
        for path, kind, n in con.execute(
            "SELECT f.path, c.kind, count(*) FROM components c "
            "JOIN files f ON f.id = c.file_id GROUP BY f.id, c.kind"
        ):
            out[path][1][kind] = n
    return out


def _total(counts: Iterable[Counts]) -> Counts:
    timelines, units = 0, Counter()
    for n, by_kind in counts:
        timelines += n
        units.update(by_kind)
    return timelines, units


def _show(counts: Counts) -> str:
    n, units = counts
    kinds = ", ".join(f"{k} {units[k]}" for k in sorted(units))
    return f"{n} timelines; {kinds or 'no units'}"


# --------------------------------------------------------------------------- #
# The check
# --------------------------------------------------------------------------- #
def _report_lines(report: ScanReport) -> list[str]:
    lines = []
    for name in ("added", "changed", "unavailable", "back"):
        for path in getattr(report, name):
            lines.append(f"  {name}: {path}")
    for old, new in report.moved:
        lines.append(f"  moved: {old} -> {new}")
    for path, line, reason in report.unreadable:
        lines.append(f"  unreadable: {path} (line {line}): {reason}")
    for group in report.shared_ids:
        lines.append(f"  shared id: {', '.join(group)}")
    if report.error:
        lines.append(f"  error: {report.error}")
    return lines


def check(folder: Path) -> bool:
    """Open ``folder`` as a corpus and print what SC-001, SC-004 and SC-005
    need. True when every check passed."""
    ok = True
    print(f"# corpus_check {folder}")
    before = listing(folder)
    sums_before = checksums(folder, before)

    started = time.perf_counter()
    corpus = open_corpus(folder, rescan_before_reads=False)
    build_time = time.perf_counter() - started
    try:
        rescan_times = []
        rescans_empty = True
        for _ in range(RESCANS):
            started = time.perf_counter()
            report = corpus.scan()
            rescan_times.append(time.perf_counter() - started)
            if report:
                rescans_empty = False
                print("a no-change rescan reported changes:")
                print("\n".join(_report_lines(report)))
        files = corpus.files()
        in_index = counts_in_index(corpus)
        shared = corpus.open_report.shared_ids
    finally:
        corpus.close()

    states = Counter(f.state for f in files)
    print(f"\n## Files: {len(files)}")
    for state in sorted(states):
        print(f"  {state}: {states[state]}")
    unreadable = [f for f in files if f.state == "unreadable"]
    if unreadable:
        print("\n## Unreadable files")
    for f in unreadable:
        own = reader_reason(folder / f.path)
        same = own == f.reason
        ok &= same
        print(f"  {f.path}: {f.reason}")
        print(f"    the reader's own reason: {'the same' if same else own}")
    if shared:
        print("\n## Files sharing a document id")
        for group in shared:
            print(f"  {', '.join(group)}")

    print("\n## Timelines and units (SC-001)")
    in_files: dict[str, Counts] = {}
    for f in files:
        if f.state == "readable":
            in_files[f.path] = counts_in_file(tla.read(folder / f.path))
    print(f"  in the files: {_show(_total(in_files.values()))}")
    print(f"  in the index: {_show(_total(in_index.values()))}")
    differ = sorted(
        p
        for p in in_files.keys() | in_index.keys()
        if in_files.get(p) != in_index.get(p)
    )
    print(f"  files that differ: {len(differ)}")
    for path in differ:
        print(
            f"    {path}: file {_show(in_files.get(path, (0, Counter())))}; "
            f"index {_show(in_index.get(path, (0, Counter())))}"
        )
    ok &= not differ

    print("\n## Times (SC-004)")
    print(f"  build: {build_time:.2f} s")
    print(f"  no-change rescans: {', '.join(f'{t:.3f}' for t in rescan_times)} s")
    ok &= rescans_empty

    after = listing(folder)
    sums_after = checksums(folder, after)
    print("\n## The folder (SC-005)")
    same_sums = sums_before == sums_after
    same_list = before == after
    print(
        f"  corpus files' SHA-256 unchanged: {'yes' if same_sums else 'NO'} "
        f"({len(sums_after)} files)"
    )
    print(
        f"  every file's size and time unchanged, none added or removed: "
        f"{'yes' if same_list else 'NO'} ({len(after)} files)"
    )
    for rel in sorted(before.keys() ^ after.keys()):
        print(f"    {'added' if rel in after else 'removed'}: {rel}")
    for rel in sorted(k for k in before.keys() & after.keys() if before[k] != after[k]):
        print(f"    changed: {rel}")
    ok &= same_sums and same_list
    return ok


# --------------------------------------------------------------------------- #
# --rescan-check
# --------------------------------------------------------------------------- #
LABEL = re.compile(rb'("label"\s*:\s*")([^"\\]+)(")')


def _writer_edit(path: Path) -> bool:
    """Add :data:`EDIT` to a label of an indexed unit of the file at ``path``,
    and write it with the core's writer. False when it has none."""
    doc = tla.read(path)
    for tl in doc.timelines.values():
        tl_kind = _kind(tl.kind)
        if tl_kind not in ("hierarchy", "marker", "range"):
            continue
        for comp in tl.components.values():
            if _kind(comp.kind) == tl_kind and comp.attrs.get("label"):
                comp.attrs["label"] = f"{comp.attrs['label']}{EDIT}"
                tla.write(path, doc)
                return True
    return False


def _text_edit(path: Path) -> bool:
    """Add :data:`EDIT` to the first non-empty label in the file's text. False
    when it has none."""
    data = path.read_bytes()
    edited, n = LABEL.subn(lambda m: m[1] + m[2] + EDIT.encode() + m[3], data, count=1)
    if not n:
        return False
    path.write_bytes(edited)
    return True


def _line_endings(path: Path) -> None:
    data = path.read_bytes()
    if b"\r\n" in data:
        path.write_bytes(data.replace(b"\r\n", b"\n"))
    else:
        path.write_bytes(data.replace(b"\n", b"\r\n"))


def dump(corpus: Corpus) -> dict[str, list[tuple]]:
    """Every row of the index, keyed by paths and uuids, sorted."""

    def order(row: tuple) -> list[tuple[bool, str]]:
        return [(v is None, "" if v is None else str(v)) for v in row]

    with corpus.reading() as r:
        return {
            table: sorted(r.connection.execute(sql).fetchall(), key=order)
            for table, sql in DUMP.items()
        }


def rescan_check(folder: Path) -> bool:
    """Apply User Story 2's changes to a copy of ``folder`` and compare its
    rescanned index with a fresh one. True when they agree and the report is
    the one expected."""
    print(f"# corpus_check --rescan-check {folder}")
    with tempfile.TemporaryDirectory(prefix="corpus-check-") as tmp:
        copy = Path(tmp, "corpus")
        shutil.copytree(folder, copy, ignore=shutil.ignore_patterns(".*"))
        corpus = open_corpus(copy, rescan_before_reads=False)
        try:
            return _apply_and_compare(corpus, copy)
        finally:
            corpus.close()


def _apply_and_compare(corpus: Corpus, copy: Path) -> bool:
    shared = {p for group in corpus.open_report.shared_ids for p in group}
    candidates = [
        f.path for f in corpus.files() if f.state == "readable" and f.path not in shared
    ]
    print(f"  readable files with their own document id: {len(candidates)}")
    if len(candidates) < 7:
        print("  too few to apply the seven changes")
        return False
    pool = iter(candidates)
    expected_changed: list[str] = []
    for kind, edit in (("the core's writer", _writer_edit), ("its text", _text_edit)):
        for path in pool:
            if edit(copy / path):
                expected_changed.append(path)
                print(f"  a label changed through {kind}: {path}")
                break
        else:
            print(f"  no file left with a label to change through {kind}")
            return False
    renamed, moved, deleted, touched, ended = (next(pool) for _ in range(5))
    renamed_to = str(
        Path(renamed).with_name("renamed-" + Path(renamed).name).as_posix()
    )
    moved_to = f"moved-by-check/{Path(moved).name}"
    (copy / renamed).rename(copy / renamed_to)
    (copy / "moved-by-check").mkdir()
    (copy / moved).rename(copy / moved_to)
    (copy / deleted).unlink()
    os.utime(copy / touched)
    _line_endings(copy / ended)
    print(f"  renamed: {renamed} -> {renamed_to}")
    print(f"  moved: {moved} -> {moved_to}")
    print(f"  deleted: {deleted}")
    print(f"  touched: {touched}")
    print(f"  line endings changed: {ended}")

    report = corpus.scan()
    print("\n## The rescan's report")
    print("\n".join(_report_lines(report)) or "  nothing")
    expected = (
        sorted(expected_changed),
        sorted([(renamed, renamed_to), (moved, moved_to)]),
        [deleted],
    )
    got = (sorted(report.changed), sorted(report.moved), sorted(report.unavailable))
    others = report.added or report.back or report.unreadable or report.error
    report_ok = got == expected and not others
    print(f"  the report expected: {'yes' if report_ok else 'NO'}")

    rescanned = dump(corpus)
    unavailable = {row[0] for row in rescanned["files"] if row[3] == "unavailable"}
    rescanned["files"] = [r for r in rescanned["files"] if r[0] not in unavailable]
    fresh_corpus = open_corpus(copy, rescan_before_reads=False)
    try:
        fresh = dump(fresh_corpus)
    finally:
        fresh_corpus.close()
    print("\n## The rescanned index against a fresh one (SC-002)")
    same = True
    for table in DUMP:
        a, b = rescanned[table], fresh[table]
        if a != b:
            same = False
            only_a = [r for r in a if r not in b]
            only_b = [r for r in b if r not in a]
            print(
                f"  {table}: {len(only_a)} rows only rescanned, "
                f"{len(only_b)} only fresh"
            )
            for row in only_a[:5]:
                print(f"    rescanned: {row}")
            for row in only_b[:5]:
                print(f"    fresh: {row}")
    if same:
        print(
            f"  same rows, apart from {len(unavailable)} unavailable file"
            f"{'' if len(unavailable) == 1 else 's'}"
        )
    return report_ok and same


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument(
        "--rescan-check",
        action="store_true",
        help="apply User Story 2's changes to a copy of the folder and compare",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )
    folder = args.folder.expanduser().resolve()
    ok = rescan_check(folder) if args.rescan_check else check(folder)
    print(f"\n{'all checks passed' if ok else 'SOME CHECKS FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
