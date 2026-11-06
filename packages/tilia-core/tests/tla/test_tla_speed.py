"""How long reading a `.tla` file takes (SC-004).

Runs only with `--run-benchmarks`, since a time taken on a busy machine says
little. From the repository's root:

    uv run --package tilia-core pytest
        packages/tilia-core/tests/tla/test_tla_speed.py --run-benchmarks

Each test prints what it measured. Only SC-004's own targets are asserted (5 MB/s, s4, a 2 MB score); the
crafted files have none. The files below are made here, laid out as the writer
lays them out, and only `read`, `canonical_bytes` and `build_time_map` are
called, so that the same file measures any branch of the core.

To time the old files of a whole corpus, set `TILIA_SPEED_CORPUS` to its folder.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tilia_core import tla
from tilia_core.timemap import build_time_map

# The writer's own, not the recording one conftest.py puts in its place during a
# test: that one would be timed too, and it checks each file against the schema.
from tilia_core.tla.writer import canonical_bytes

pytestmark = pytest.mark.benchmark

HERE = Path(__file__).resolve().parent
OLD = HERE / "old"

# SC-004's targets.
AT_LEAST_MB_PER_SECOND = 5.0  # about 30 microseconds per component
WITH_A_2_MB_SCORE = 0.100
CORPUS_OF_OLD_FILES = 5.0
SCORE_BYTES = 2_000_000

BASE_MS = 1_767_225_600_000  # the golden files' first id


def make_id(n: int) -> str:
    """The n-th id, a UUIDv7: in id order, as the writer writes them."""
    return str(uuid.UUID(int=(BASE_MS + n) << 80 | 7 << 76 | 0b10 << 62 | n))


def as_written(
    kind: str,
    components: list[dict[str, Any]],
    *,
    length: float | None,
    scores: tuple[dict[str, Any], ...] = (),
    **timeline: Any,
) -> bytes:
    """A file of one timeline, in the current format."""
    content = {
        "app_name": "TiLiA",
        "version": tla.FORMAT_VERSION,
        "document_id": make_id(0),
        "time_unit": "seconds",
        "media": {"path": "", "length": length},
        "metadata": {"title": "Speed", "notes": ""},
        "timelines": {
            make_id(1): {
                "kind": kind,
                "ordinal": 1,
                "height": 60,
                **timeline,
                "components": {
                    make_id(10 + n): component for n, component in enumerate(components)
                },
            }
        },
        "scores": list(scores),
    }
    return (json.dumps(content, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def beats(count: int) -> bytes:
    """Bars of four beats."""
    components: list[dict[str, Any]] = [
        {"kind": "BEAT", "time": n * 0.25, "measure": {}}
        if n % 4 == 0
        else {"kind": "BEAT", "time": n * 0.25}
        for n in range(count)
    ]
    return as_written("Beat", components, length=count * 0.25)


def flat_hierarchies(count: int, *, length: bool = True) -> bytes:
    """Hierarchies side by side, at one level."""
    components = [
        {
            "kind": "HIERARCHY",
            "start": float(n),
            "end": float(n + 1),
            "level": 1,
            "label": f"section {n}",
        }
        for n in range(count)
    ]
    return as_written("Hierarchy", components, length=float(count) if length else None)


def ranges_in_rows(count: int) -> bytes:
    """As many rows as ranges, one range in each."""
    rows = [{"id": f"r{n:05d}", "name": f"Row {n}"} for n in range(count)]
    components = [
        {
            "kind": "RANGE",
            "start": float(n),
            "end": float(n + 1),
            "row_id": f"r{n:05d}",
            "label": f"range {n}",
        }
        for n in range(count)
    ]
    return as_written("Range", components, length=float(count), rows=rows)


def score_lines() -> list[str]:
    """About 2 MB of lines, as a score holds them."""
    line = '<note xml:id="n{:07d}" pname="c" oct="4" dur="4" stem.dir="up"/>'
    lines = []
    size = 0
    while size < SCORE_BYTES:
        lines.append(line.format(len(lines)))
        size += len(lines[-1])
    return lines


def with_a_score(fields: dict[str, Any]) -> bytes:
    score = {"id": make_id(5), **fields}
    return as_written("Score", [], length=10.0, scores=(score,), score=score["id"])


def with_an_mei_score() -> bytes:
    return with_a_score(
        {
            "format": "mei",
            "source": {"file": "piece.musicxml", "origin": "made for this test"},
            "license": "CC0-1.0",
            "content": score_lines(),
        }
    )


def with_a_legacy_score() -> bytes:
    return with_a_score(
        {"format": "svg-osmd-legacy", "content": score_lines(), "beat_x": []}
    )


def old_file_with_an_svg() -> bytes:
    """A file of TiLiA 0.7.0 whose score timeline holds an SVG of about 2 MB."""
    content = json.loads((OLD / "0.7.0-osmd.tla").read_bytes())
    score = next(
        timeline
        for timeline in content["timelines"].values()
        if timeline["kind"] == "Score"
    )
    score["svg_data"] = "\n".join(score_lines())
    return json.dumps(content, indent=2, ensure_ascii=False).encode("utf-8")


def misplaced_closing_taps_in_one_bar(count: int) -> bytes:
    """One bar whose last beat comes after all of its closing taps, so that each
    of them is read as an ordinary beat."""
    taps = [
        {"kind": "BEAT", "time": float(n + 1), "closing": True} for n in range(count)
    ]
    return as_written(
        "Beat",
        [
            {"kind": "BEAT", "time": 0.0, "measure": {}},
            *taps,
            {"kind": "BEAT", "time": float(count + 1)},
        ],
        length=float(count + 2),
    )


def closed_movements(count: int) -> bytes:
    """Movements of one bar of two beats, each ended by a closing tap."""
    components: list[dict[str, Any]] = []
    for n in range(count):
        downbeat = {"restart": True} if n else {}
        components += [
            {"kind": "BEAT", "time": n * 4.0, "measure": downbeat},
            {"kind": "BEAT", "time": n * 4.0 + 1.0},
            {"kind": "BEAT", "time": n * 4.0 + 2.0, "closing": True},
        ]
    return as_written("Beat", components, length=count * 4.0)


# Made here, so what the writer writes as it is, without a warning.
MADE_HERE: dict[str, Callable[[], bytes]] = {
    "10,000 beats": lambda: beats(10_000),
    "10,000 flat hierarchies": lambda: flat_hierarchies(10_000),
    "10,000 flat hierarchies, no length": lambda: flat_hierarchies(
        10_000, length=False
    ),
    "50,000 flat hierarchies": lambda: flat_hierarchies(50_000),
    "4,000 ranges in 4,000 rows": lambda: ranges_in_rows(4_000),
    "a 2 MB MEI score": with_an_mei_score,
}
GOLDEN = HERE / "golden" / "every-kind.tla"
# The largest of the tests' old files, read through the migration.
OLD_FILES: dict[str, Path] = {
    "the largest old file, 1000 beats": OLD / "0.5.15.0-many-beats.tla",
    "an old file of s4": OLD / "0.6.0-s4-10.tla",
    "an old file with a score": OLD / "0.7.0-osmd.tla",
}
WITH_A_SCORE: dict[str, Callable[[], bytes]] = {
    "MEI": with_an_mei_score,
    "legacy": with_a_legacy_score,
    "old file's SVG": old_file_with_an_svg,
}
CRAFTED: dict[str, Callable[[], bytes]] = {
    "one bar with 8,000 misplaced closing taps": lambda: (
        misplaced_closing_taps_in_one_bar(8_000)
    ),
    "8,000 closed movements": lambda: closed_movements(8_000),
}


def runs_for(data: bytes) -> int:
    """More runs for a small file, where one run says less."""
    return 30 if len(data) < 200_000 else 20 if len(data) < 5_000_000 else 3


def fastest(run: Callable[[], Any], times: int) -> float:
    """The fewest seconds `run` took: the run the machine disturbed least."""
    seconds = []
    for _ in range(times):
        start = time.perf_counter()
        run()
        seconds.append(time.perf_counter() - start)
    return min(seconds)


def round_trip(path: Path) -> float:
    """The seconds a JSON round trip of `path` took."""
    start = time.perf_counter()
    json.dumps(json.loads(path.read_bytes()), indent=2, ensure_ascii=False)
    return time.perf_counter() - start


def read_and_write(path: Path) -> tuple[float, float]:
    """The seconds `read` took, and `canonical_bytes`, with the garbage collector
    at work in both, as in any read of a corpus."""
    start = time.perf_counter()
    document = tla.read(path)
    middle = time.perf_counter()
    canonical_bytes(document)
    return middle - start, time.perf_counter() - middle


def ms(seconds: float) -> str:
    return f"{seconds * 1000:.1f} ms"


def mb(data: bytes) -> str:
    return f"{len(data) / 1_000_000:.2f} MB"


def megabytes_per_second(name: str, data: bytes, path: Path, capsys: Any) -> float:
    """The megabytes of `path` that `read` and `canonical_bytes` get through in a
    second, in the run of each that the machine disturbed least. Prints that, and
    how many times a JSON round trip the two take, for information."""
    json_runs, read_runs, write_runs = [], [], []
    for _ in range(runs_for(data)):
        json_runs.append(round_trip(path))
        read_run, write_run = read_and_write(path)
        read_runs.append(read_run)
        write_runs.append(write_run)
    together = min(map(sum, zip(read_runs, write_runs, strict=True)))
    speed = len(data) / 1_000_000 / together
    with capsys.disabled():
        print(
            f"\n{name}: {mb(data)}: read {ms(min(read_runs))},"
            f" canonical_bytes {ms(min(write_runs))}, together {ms(together)}:"
            f" {speed:.1f} MB/s; {together / min(json_runs):.1f} times a JSON round trip"
        )
    return speed


@pytest.mark.parametrize("name", MADE_HERE)
def test_a_file_made_here_is_read_at_5_mb_per_second(name, tmp_path, capsys):
    data = MADE_HERE[name]()
    path = tmp_path / "piece.tla"
    path.write_bytes(data)
    document = tla.read(path)
    assert not document.warnings
    assert canonical_bytes(document) == data

    assert megabytes_per_second(name, data, path, capsys) >= AT_LEAST_MB_PER_SECOND


def test_the_largest_golden_file_is_read_at_5_mb_per_second(tmp_path, capsys):
    data = GOLDEN.read_bytes()
    path = tmp_path / "piece.tla"
    path.write_bytes(data)

    speed = megabytes_per_second("the largest golden file", data, path, capsys)

    assert speed >= AT_LEAST_MB_PER_SECOND


@pytest.mark.parametrize("name", OLD_FILES)
def test_an_old_file_is_timed(name, tmp_path, capsys):
    """No target: SC-004's 5 MB/s is for the new format, and an old file is
    migrated as it is read, which is more work. s4's own target covers them."""
    data = OLD_FILES[name].read_bytes()
    path = tmp_path / "piece.tla"
    path.write_bytes(data)

    megabytes_per_second(name, data, path, capsys)


@pytest.mark.parametrize("name", WITH_A_SCORE)
def test_a_file_with_a_2_mb_score_takes_under_100_ms(name, tmp_path, capsys):
    data = WITH_A_SCORE[name]()
    path = tmp_path / "piece.tla"
    path.write_bytes(data)
    held = sum(
        len(line) for score in tla.read(path).scores.values() for line in score.lines
    )
    assert held >= SCORE_BYTES

    seconds = fastest(lambda: canonical_bytes(tla.read(path)), runs_for(data))

    with capsys.disabled():
        print(f"\na 2 MB score, {name}: {mb(data)}: {ms(seconds)}")
    assert seconds < WITH_A_2_MB_SCORE


def test_the_old_files_of_a_corpus(capsys):
    """SC-004 counts on a laptop, for s4's files. Without a corpus, as many reads
    of the one file of s4 that the tests have stand in for them, with no target,
    since a file isn't a corpus and a runner isn't a laptop."""
    folder = os.environ.get("TILIA_SPEED_CORPUS")
    paths = (
        sorted(Path(folder).rglob("*.tla"))
        if folder
        else [OLD / "0.6.0-s4-10.tla"] * 234
    )

    def read_all() -> None:
        for path in paths:
            tla.read(path)

    seconds = fastest(read_all, 3)

    with capsys.disabled():
        print(f"\n{folder or 'one old file'}: {len(paths)} reads: {seconds:.2f} s")
    if folder:
        assert seconds < CORPUS_OF_OLD_FILES


@pytest.mark.parametrize("name", CRAFTED)
def test_a_crafted_file_with_closing_taps(name, tmp_path, capsys):
    """Real files don't reach this, and there is no target: it is here to be seen
    (`timemap._rows`, `_beats_with` and its caller)."""
    data = CRAFTED[name]()
    path = tmp_path / "piece.tla"
    path.write_bytes(data)
    document = tla.read(path)
    assert canonical_bytes(document) == data
    timeline = next(iter(document.timelines.values()))

    read_and_write_seconds = fastest(
        lambda: canonical_bytes(tla.read(path)), runs_for(data)
    )
    start = time.perf_counter()
    time_map, reason = build_time_map(document, timeline)
    time_map_seconds = time.perf_counter() - start

    assert time_map is not None, reason
    with capsys.disabled():
        print(
            f"\n{name}: {mb(data)}: read and canonical_bytes"
            f" {ms(read_and_write_seconds)}; build_time_map {ms(time_map_seconds)}"
        )
