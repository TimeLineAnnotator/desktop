"""Running a function on many arguments in worker processes, for a scan that
reads many files (TimeLineAnnotator/project-management#156).

Each worker is a fresh interpreter, ``sys.executable -c ...``, with this
process's ``sys.path``. It imports the core, and nothing of the program that
started it: ``multiprocessing``'s ``spawn``, the only way it starts processes
on Windows, runs the program's main module again in every worker, so that a
script that opens a corpus without ``if __name__ == "__main__"`` would run
once per worker. Tasks and results go through the workers' standard input
and output, pickled; their standard error is this process's.

A program frozen into an executable has no interpreter to start:
:func:`available` is false there, and the caller does the work itself.
"""

from __future__ import annotations

import os
import pickle
import subprocess
import sys
import threading
from collections.abc import Callable, Sequence
from typing import IO, Any

_BOOT = (
    "import pickle, sys\n"
    "sys.path[:] = pickle.load(sys.stdin.buffer)\n"
    "from tilia_core.corpus._workers import serve\n"
    "serve()\n"
)
"""What a worker runs: this process's ``sys.path``, then :func:`serve`."""


class WorkersFailed(Exception):
    """The workers couldn't start, or one stopped before giving every result."""


def available() -> bool:
    """Whether workers can be started: not in a program frozen into an
    executable, whose ``sys.executable`` is the program."""
    frozen = getattr(sys, "frozen", False) or "__compiled__" in globals()
    return bool(sys.executable) and not frozen


def serve() -> None:
    """A worker's loop: reads pickled ``(function, arguments)`` from standard
    input until it ends, and writes each call's result, pickled, to standard
    output. What the function prints goes to standard error."""
    tasks = sys.stdin.buffer
    results = sys.stdout.buffer
    sys.stdout = sys.stderr
    while True:
        try:
            function, arguments = pickle.load(tasks)
        except EOFError:
            return
        pickle.dump(function(*arguments), results, protocol=pickle.HIGHEST_PROTOCOL)
        results.flush()


def run(
    function: Callable[..., Any], tasks: Sequence[tuple[Any, ...]], workers: int
) -> list[Any]:
    """``function(*task)`` for each of ``tasks``, in ``workers`` processes,
    in the tasks' order. ``function``, its arguments and its results must
    pickle, and ``function`` must be importable by name. Raises
    :class:`WorkersFailed` when a worker can't start or stops early;
    ``function`` itself should raise nothing."""
    results: list[Any] = [None] * len(tasks)
    next_task = iter(range(len(tasks)))
    taking = threading.Lock()
    errors: list[BaseException] = []
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    processes: list[subprocess.Popen[bytes]] = []

    def work(process: subprocess.Popen[bytes]) -> None:
        assert process.stdin is not None and process.stdout is not None
        try:
            _send(process.stdin, sys.path)
            while not errors:
                with taking:
                    n = next(next_task, None)
                if n is None:
                    break
                _send(process.stdin, (function, tasks[n]))
                results[n] = pickle.load(process.stdout)
        except BaseException as err:  # noqa: BLE001 - raised in the caller
            errors.append(err)
        finally:
            try:
                process.stdin.close()  # the worker's end of its tasks
            except OSError:
                pass

    finished = False
    try:
        for _ in range(workers):
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-c", _BOOT],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    creationflags=flags,
                )
            )
        threads = [
            threading.Thread(target=work, args=(p,), daemon=True) for p in processes
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        finished = not errors
    except OSError as err:
        raise WorkersFailed(f"a worker couldn't start: {err}") from err
    finally:
        for process in processes:
            if not finished:
                process.kill()
            process.wait()
            if process.stdout is not None:
                process.stdout.close()
    if errors:
        err = errors[0]
        if isinstance(err, EOFError):
            raise WorkersFailed("a worker stopped before giving its result") from err
        raise WorkersFailed(f"{type(err).__name__}: {err}") from err
    return results


def _send(stream: IO[bytes], value: object) -> None:
    pickle.dump(value, stream, protocol=pickle.HIGHEST_PROTOCOL)
    stream.flush()


def cpus() -> int:
    """How many CPUs this process may use."""
    if hasattr(os, "sched_getaffinity"):
        return len(os.sched_getaffinity(0))
    return os.cpu_count() or 1


__all__ = ["WorkersFailed", "available", "cpus", "run", "serve"]
