from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal, Slot

# Keeps (QThread, _Worker, _ResultRelay) tuples alive for the duration of
# each background task. Without this, nothing holds a Python reference to
# them once run_in_background() returns, and Qt/shiboken can tear down the
# underlying C++ objects while the thread is still running.
_active_tasks: set[tuple] = set()


class _Worker(QObject):
    done = Signal(object)
    failed = Signal(object)

    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self._fn = fn

    @Slot()
    def run(self) -> None:
        try:
            result = self._fn()
        except Exception as e:
            self.failed.emit(e)
            return
        self.done.emit(result)


class _ResultRelay(QObject):
    """Lives on the GUI thread (never moved), so connecting the worker's
    signals to this object's slots auto-resolves to a queued connection.
    Connecting worker signals directly to a plain function/lambda instead
    would run that callback on the worker thread -- Qt can only infer
    thread affinity, and therefore whether to queue, for a real QObject."""

    def __init__(
        self,
        thread: QThread,
        on_done: Callable[[object], None] | None,
        on_error: Callable[[Exception], None] | None,
    ) -> None:
        super().__init__()
        self._thread = thread
        self._on_done = on_done
        self._on_error = on_error

    @Slot(object)
    def handle_done(self, result: object) -> None:
        if self._on_done:
            self._on_done(result)
        self._cleanup()

    @Slot(object)
    def handle_error(self, exc: Exception) -> None:
        if self._on_error:
            self._on_error(exc)
        self._cleanup()

    def _cleanup(self) -> None:
        self._thread.quit()
        self._thread.wait()
        _active_tasks.discard(self._task_key)


def run_in_background(
    fn: Callable[[], object],
    on_done: Callable[[object], None] | None = None,
    on_error: Callable[[Exception], None] | None = None,
) -> None:
    """
    Runs `fn` on a dedicated worker QThread and returns immediately.

    `fn` must be Qt-free: it must not call tilia.requests.post()/get()
    (tilia/requests/ has no cross-thread marshaling) and must not touch any
    Qt widget. `on_done`/`on_error` run back on the GUI thread once `fn`
    finishes, so they may safely call post()/get() and touch widgets.
    """
    thread = QThread()
    worker = _Worker(fn)
    worker.moveToThread(thread)
    relay = _ResultRelay(thread, on_done, on_error)

    task = (thread, worker, relay)
    relay._task_key = task

    worker.done.connect(relay.handle_done)
    worker.failed.connect(relay.handle_error)
    thread.started.connect(worker.run)

    _active_tasks.add(task)
    thread.start()
