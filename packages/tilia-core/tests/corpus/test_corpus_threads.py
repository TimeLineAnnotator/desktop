"""Queries in four threads while the files change and the corpus is rescanned
(SC-007): no result mixes two generations, and nothing fails.

The writer records what every query gives at each generation. Readers keep what
they got, and the answers are compared once all the threads have ended, so how
fast any thread runs decides only how many answers there are to compare. The
length is a lower bound: on a slow machine the writer goes on until every reader
has seen the corpus change. Only a stuck thread fails on time, long after that.
"""

import itertools
import os
import random
import threading
import time
import traceback
from typing import Any

import corpus_docs
from json_reader import JsonDocumentReader

from tilia_core import open_corpus, tql

LENGTH = 60.0 if os.environ.get("TILIA_CORE_LONG_TESTS") == "1" else 5.0
"""Seconds the writer keeps changing files, at the least."""

STUCK_AFTER = LENGTH + 300.0
"""Seconds after which a thread that hasn't ended counts as stuck."""

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


def record(corpus: Any, expected: dict[int, dict[str, str]]) -> None:
    """What every query gives at the current generation, into ``expected``."""
    with corpus.reading() as read:
        generation = read.generation
        answers = {}
        for query in QUERIES:
            result = tql.run(corpus, query)
            assert result.generation == generation
            answers[query] = answer(result)
    assert expected.setdefault(generation, answers) == answers


def test_results_keep_to_one_generation_while_the_corpus_changes(tmp_path):
    present = set(PIECES[:6])
    for name in present:
        corpus_docs.write_doc(tmp_path / f"{name}.tla", piece(name, 0))
    corpus = open_corpus(
        tmp_path, reader=JsonDocumentReader(), rescan_before_reads=False
    )
    record(corpus, expected := {})

    errors: list[str] = []
    writer_done = threading.Event()
    lock = threading.Lock()
    answers: list[dict[tuple[str, int], set[str]]] = [{} for _ in range(READERS)]
    generations: list[set[int]] = [set() for _ in range(READERS)]

    def read(number: int) -> None:
        try:
            for query in itertools.cycle(QUERIES):
                if writer_done.is_set():
                    return
                result = tql.run(corpus, query)
                key = (query, result.generation)
                answers[number].setdefault(key, set()).add(answer(result))
                with lock:
                    generations[number].add(result.generation)
        except BaseException:  # noqa: BLE001 - told at the end, whatever it was
            errors.append(traceback.format_exc())

    def every_reader_saw_a_change() -> bool:
        with lock:
            return all(len(seen) >= 2 for seen in generations)

    def write() -> None:
        try:
            rng = random.Random(13)
            deadline = time.monotonic() + LENGTH
            for take in itertools.count(1):
                if errors or (
                    time.monotonic() >= deadline and every_reader_saw_a_change()
                ):
                    return
                edited = rng.choice(sorted(present))
                corpus_docs.write_doc(tmp_path / f"{edited}.tla", piece(edited, take))
                absent = sorted(set(PIECES) - present)
                if absent:
                    added = rng.choice(absent)
                    corpus_docs.write_doc(tmp_path / f"{added}.tla", piece(added, take))
                    present.add(added)
                if len(present) > 3:
                    deleted = rng.choice(sorted(present - {edited}))
                    (tmp_path / f"{deleted}.tla").unlink()
                    present.remove(deleted)
                report = corpus.scan()
                assert report.error is None
                record(corpus, expected)
        except BaseException:  # noqa: BLE001 - told at the end, whatever it was
            errors.append(traceback.format_exc())
        finally:
            writer_done.set()

    threads = [
        threading.Thread(target=read, args=(number,), daemon=True)
        for number in range(READERS)
    ]
    threads.append(threading.Thread(target=write, daemon=True))
    for thread in threads:
        thread.start()
    give_up = time.monotonic() + STUCK_AFTER
    for thread in threads:
        thread.join(max(0.0, give_up - time.monotonic()))
    stuck = [thread.name for thread in threads if thread.is_alive()]
    # not closed then: closing would wait for the stuck thread's read
    assert not stuck, f"stuck after {STUCK_AFTER} s: {stuck}\n{errors}"
    corpus.close()

    assert errors == [], "\n".join(errors)
    assert len(expected) > 2
    for number in range(READERS):
        assert len(generations[number]) >= 2
        for (query, generation), got in answers[number].items():
            assert generation in expected, (query, generation)
            assert got == {expected[generation][query]}, (number, query, generation)
