"""Queries in four threads while the files change and the corpus is rescanned
(SC-007): no result mixes two generations, and nothing fails.

A writer thread edits, adds and deletes files, in an order a seeded random
generator gives, and scans; after each scan it records, inside one read, what
every query gives at the new generation. Four reader threads run the queries
over and over. Before each change the writer waits until every reader has
finished a query on the current generation, so every reader has answers at
every generation however the threads are scheduled. The answers are compared
once the threads have ended: each must be the writer's record for the
generation it carries.

The run is bounded: ``MIN_SCANS`` scans, then more until ``LENGTH`` seconds
have passed, never more than ``MAX_SCANS``. The scenario's own thread watches
the others: when no thread has got any further for ``STALL`` seconds, or the
run is longer than ``DEADLINE``, it fails at once with how far the run got and
the stack of every thread still running. A slow thread is left to
``DEADLINE`` while the others get on. The scenario runs in a child process,
because a fault can also freeze the whole process: two threads on one
connection block inside sqlite3 with the GIL held (``tql/inuse.py``), and no
thread of the process runs again. ``faulthandler`` then prints every thread's
stack and ends the child ``FROZEN`` seconds after the scenario began, and it
does the same if the child crashes.

In the child, threads take turns more often (``SWITCH``) and a change makes new
reads wait sooner (``PATIENCE``), so that the run holds more scans, and a
reader can come in at more places in a change. That assumes the child has more
than one CPU to share with whatever else runs, as CI's runners have. On one
CPU shared with busy processes, each turn waits for the system's scheduler,
and the run takes several times as long.
"""

import faulthandler
import itertools
import os
import random
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

import corpus_docs
import pytest
from json_reader import JsonDocumentReader

from tilia_core import open_corpus, tql
from tilia_core.corpus import store

LONG = os.environ.get("TILIA_CORE_LONG_TESTS") == "1"
LENGTH = 60.0 if LONG else 5.0
"""Seconds the writer goes on changing files and scanning; it makes
``MIN_SCANS`` scans however long they take."""
MIN_SCANS = 3
MAX_SCANS = 1000 if LONG else 100
"""Scans the writer never goes beyond, however fast they are."""
STALL = 20.0
"""Seconds in which no thread finished a query or a step of the writer, after
which the run counts as stuck."""
DEADLINE = LENGTH + 115.0
"""Seconds after which the run fails, even while its threads get on. A run
takes about 7 s; on one CPU shared with four busy processes, its three scans
took 42 to 84 s."""
FROZEN = DEADLINE + 30.0
"""Seconds from the start of the scenario after which the child counts as
frozen: past ``DEADLINE``, with time for the scenario's own report, which
comes slowly on a busy machine."""
STARTING = 120.0
"""Seconds the child may take to start the scenario, its imports included."""
SEED = 13
SWITCH = 1e-4
"""The child's switch interval, in seconds: 50 times as often as Python's
default. With the default, a reader almost never comes in between the end of
a change and its next few statements."""
DEFAULT_SWITCH = sys.getswitchinterval()
PATIENCE = 0.05
"""Seconds a change waits for running reads in the child before new reads wait
for it (``store.PATIENCE``, 2 s): with 2 s, the 5 s hold three scans. It also
bounds how long ``apply`` retries a lock error: 50 ms here instead of 2 s. A
change of a correct store meets no lock error here, since it waits for the
reads."""

READERS = 4
PIECES = [f"piece{n:02}" for n in range(12)]
QUERIES = (
    "verse IN form",
    "chorus IN form",
    "* IN form",
    "verse THEN * IN form",
    "*[start >= 10] IN form",
)


def piece(name: str, take: int) -> corpus_docs.Document:
    """Units of ``name`` that differ with ``take``, and in how many there are."""
    labels = ["verse", f"take{take}", "chorus"] + ["verse"] * (take % 3)
    units = [[label, 1, 10 * i, 10 * (i + 1)] for i, label in enumerate(labels)]
    return corpus_docs.document(
        corpus_docs.hierarchy(units, fields={"role": "form"}), document_id=name
    )


def answer(result: tql.Result) -> str:
    return repr((result.rows, result.warnings))


def record(corpus: Any, expected: dict[int, dict[str, str]]) -> int:
    """What every query gives at the current generation, into ``expected``;
    returns the generation."""
    with corpus.reading() as read:
        generation = read.generation
        answers = {}
        for query in QUERIES:
            result = tql.run(corpus, query)
            assert result.generation == generation, (query, result.generation)
            answers[query] = answer(result)
    recorded = expected.setdefault(generation, answers)
    assert recorded == answers, f"generation {generation} changed:\n{recorded}"
    return generation


def stacks(threads: list[threading.Thread], doing: dict[str, str]) -> str:
    """The innermost frames of every thread of ``threads`` still running, and
    what it was doing."""
    frames = sys._current_frames()
    out = []
    for thread in threads:
        frame = frames.get(thread.ident) if thread.ident is not None else None
        if thread.is_alive() and frame is not None:
            stack = "".join(traceback.format_stack(frame, limit=8))
            out.append(f"--- {thread.name}, {doing[thread.name]}:\n{stack}")
    return "\n".join(out)


def scenario(folder: Path) -> None:
    """The run, in ``folder``; raises ``AssertionError`` when it fails."""
    present = set(PIECES[:6])
    for name in present:
        corpus_docs.write_doc(folder / f"{name}.tla", piece(name, 0))
    corpus = open_corpus(folder, reader=JsonDocumentReader(), rescan_before_reads=False)
    expected: dict[int, dict[str, str]] = {}

    names = [f"reader {number}" for number in range(READERS)] + ["writer"]
    cond = threading.Condition()
    stop = threading.Event()
    errors: list[str] = []
    # Each thread writes only its own entries, so these need no lock. The
    # readers take ``cond`` only when their generation moves: taking it with
    # every query kept the writer waiting to take it back, on a busy machine.
    progress = dict.fromkeys(names, time.monotonic())  # when each last got on
    doing = dict.fromkeys(names, "starting")
    latest = [0] * READERS  # the latest generation each reader has answers at
    finished = [0] * READERS  # how many queries each reader has finished
    answers: list[dict[tuple[str, int], set[str]]] = [{} for _ in range(READERS)]

    def step(name: str, what: str) -> None:
        progress[name] = time.monotonic()
        doing[name] = what

    def fail(name: str) -> None:
        errors.append(f"{name}:\n{traceback.format_exc()}")
        stop.set()
        with cond:
            cond.notify_all()

    def read(number: int) -> None:
        name = names[number]
        try:
            for query in itertools.cycle(QUERIES[number:] + QUERIES[:number]):
                if stop.is_set():
                    return
                step(name, f"running {query!r}")
                result = tql.run(corpus, query)
                generation = result.generation
                key = (query, generation)
                answers[number].setdefault(key, set()).add(answer(result))
                finished[number] += 1
                if generation > latest[number]:
                    with cond:
                        latest[number] = generation
                        cond.notify_all()
        except BaseException:  # noqa: BLE001 - told at the end, whatever it was
            fail(name)

    def readers_caught_up(generation: int) -> None:
        """Wait until every reader has finished a query on ``generation``; a
        slow reader is left to ``DEADLINE``."""
        step("writer", f"waiting for every reader to read generation {generation}")
        with cond:
            cond.wait_for(lambda: stop.is_set() or min(latest) >= generation, DEADLINE)
            behind = [names[n] for n in range(READERS) if latest[n] < generation]
        assert stop.is_set() or not behind, f"{behind} never read {generation}"

    def write() -> None:
        try:
            rng = random.Random(SEED)
            step("writer", "recording the first generation")
            readers_caught_up(record(corpus, expected))
            ends = time.monotonic() + LENGTH
            for take in range(1, MAX_SCANS + 1):
                if stop.is_set() or (take > MIN_SCANS and time.monotonic() >= ends):
                    return
                step("writer", f"changing files for scan {take}")
                edited = rng.choice(sorted(present))
                corpus_docs.write_doc(folder / f"{edited}.tla", piece(edited, take))
                added = rng.choice(sorted(set(PIECES) - present))
                corpus_docs.write_doc(folder / f"{added}.tla", piece(added, take))
                present.add(added)
                deleted = rng.choice(sorted(present - {edited, added}))
                (folder / f"{deleted}.tla").unlink()
                present.remove(deleted)
                step("writer", f"scan {take}")
                report = corpus.scan()
                assert report.error is None, report.error
                # a file added and one deleted: the generation always moves
                assert report.generation_after > report.generation_before, report
                step("writer", f"recording generation {report.generation_after}")
                readers_caught_up(record(corpus, expected))
        except BaseException:  # noqa: BLE001 - told at the end, whatever it was
            fail("writer")
        finally:
            stop.set()

    threads = [
        threading.Thread(target=read, args=(number,), name=names[number], daemon=True)
        for number in range(READERS)
    ]
    threads.append(threading.Thread(target=write, name="writer", daemon=True))
    started = time.monotonic()
    for thread in threads:
        thread.start()
    while running := [thread for thread in threads if thread.is_alive()]:
        running[0].join(0.1)
        now = time.monotonic()
        idle = now - max(progress.values())
        if idle > STALL or now - started > DEADLINE:
            got = f"{len(expected) - 1} scans; queries per reader: {finished}"
            sys.setswitchinterval(DEFAULT_SWITCH)  # the report needs its turns
            why = (
                f"no thread got any further for {STALL:.0f} s"
                if idle > STALL
                else f"the run took longer than {DEADLINE:.0f} s"
            )
            frames = stacks(threads, doing)
            stop.set()
            # not closed: closing would wait for a stuck thread's read
            raise AssertionError(f"{why} ({got})\n{frames}\n" + "\n".join(errors))
    corpus.close()

    assert errors == [], "\n".join(errors)
    assert len(expected) > MIN_SCANS, sorted(expected)
    for number in range(READERS):
        seen = {generation for _, generation in answers[number]}
        assert seen == set(expected), (names[number], sorted(seen), sorted(expected))
        for (query, generation), got in answers[number].items():
            want = expected[generation][query]
            assert got == {want}, (
                f"{names[number]} got, for {query!r} at generation {generation}:\n"
                + "\n".join(sorted(got - {want}))
                + f"\nwhere the writer recorded:\n{want}"
            )
    print(f"{len(expected) - 1} scans in {time.monotonic() - started:.1f} s")


def main(folder: str) -> None:
    """Run in the child process: the scenario, then exit at once, without
    waiting for a thread stuck inside sqlite3."""
    faulthandler.dump_traceback_later(FROZEN, exit=True)  # from now, not the start
    sys.setswitchinterval(SWITCH)
    store.PATIENCE = PATIENCE
    try:
        scenario(Path(folder))
    except BaseException:  # noqa: BLE001 - told on stderr, whatever it was
        sys.setswitchinterval(DEFAULT_SWITCH)
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(1)
    print("SCENARIO OK", flush=True)
    os._exit(0)


def text(output: str | bytes | None) -> str:
    """What a child wrote: ``TimeoutExpired`` gives bytes on some systems,
    even with ``text=True``."""
    if isinstance(output, bytes):
        return output.decode(errors="replace")
    return output or ""


def test_results_keep_to_one_generation_while_the_corpus_changes(tmp_path):
    code = (
        f"import sys; sys.path[:0] = {sys.path!r}\n"
        "import faulthandler; faulthandler.enable()\n"
        f"faulthandler.dump_traceback_later({STARTING}, exit=True)\n"
        "import test_corpus_threads\n"
        "test_corpus_threads.main(sys.argv[1])\n"
    )
    try:
        done = subprocess.run(
            [sys.executable, "-c", code, str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=STARTING + FROZEN + 30.0,
        )
    except subprocess.TimeoutExpired as err:
        pytest.fail(f"the child didn't end:\n{text(err.stdout)}\n{text(err.stderr)}")
    print(done.stdout, end="")  # how many scans, shown with -s
    if done.returncode != 0 or "SCENARIO OK" not in done.stdout:
        pytest.fail(
            f"the child ended with {done.returncode}\n"
            f"stdout:\n{done.stdout}\nstderr:\n{done.stderr}",
            pytrace=False,
        )
