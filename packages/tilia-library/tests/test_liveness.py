from __future__ import annotations

import json
import logging
import threading
import time

import pytest
from conftest import send
from support.fixture_backend import FixtureBackend

from tilia_library.api import register_all
from tilia_library.corpora import Corpora
from tilia_library.liveness import Liveness
from tilia_library.server import LibraryServer


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class ScanBackend(FixtureBackend):
    """Records its scans; ``cost`` is how long (on the fake clock) each takes."""

    def __init__(self, clock: FakeClock | None = None) -> None:
        super().__init__()
        self.clock = clock
        self.cost = 0.0
        self.scans: list[float] = []
        self.gen = 1
        self.finds_change = False
        self.rows: list[dict] | None = None
        self.fail = False
        self.gate: threading.Event | None = None

    def scan(self, corpus):
        self.scans.append(self.clock.now if self.clock else 0.0)
        if self.gate is not None:
            self.gate.wait(5)
        if self.clock:
            self.clock.now += self.cost
        if self.fail:
            raise RuntimeError("boom")
        if self.finds_change:
            self.gen += 1
            self.finds_change = False
        return super().scan(corpus)

    def generation(self, corpus):
        return self.gen

    def files(self, corpus):
        return self.rows if self.rows is not None else super().files(corpus)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def backend(clock):
    return ScanBackend(clock)


@pytest.fixture
def folder(tmp_path):
    folder = tmp_path / "pieces"
    folder.mkdir()
    return folder


@pytest.fixture
def corpora(tmp_path, folder):
    listed = Corpora(tmp_path / "library.toml")
    listed.add(folder)
    return listed


@pytest.fixture
def corpus(corpora):
    return corpora.all()[0]


@pytest.fixture
def liveness(backend, clock):
    return Liveness(backend, clock=clock)


def test_first_rescan_is_due_after_the_interval(liveness, backend, clock, corpus):
    liveness.watch(corpus.id, corpus, "h")
    clock.now = 2.9
    liveness.tick()
    assert backend.scans == []
    clock.now = 3.0
    liveness.tick()
    assert backend.scans == [3.0]
    clock.now = 5.9
    liveness.tick()
    clock.now = 6.0
    liveness.tick()
    assert backend.scans == [3.0, 6.0]


def test_watching_again_does_nothing(liveness, backend, clock, corpus):
    liveness.watch(corpus.id, corpus, "h")
    clock.now = 2.0
    liveness.watch(corpus.id, corpus, "h")
    clock.now = 3.0
    liveness.tick()
    assert backend.scans == [3.0]


def test_slow_scans_push_the_next_one_back(liveness, backend, clock, corpus):
    backend.cost = 1.0
    liveness.watch(corpus.id, corpus, "h")
    clock.now = 3.0
    liveness.tick()
    assert clock.now == 4.0
    clock.now = 13.9
    liveness.tick()
    assert len(backend.scans) == 1
    clock.now = 14.0
    liveness.tick()
    assert len(backend.scans) == 2


def test_poke_makes_the_corpus_due_now(liveness, backend, clock, corpus):
    liveness.watch(corpus.id, corpus, "h")
    liveness.poke("nope-0000")
    liveness.tick()
    assert backend.scans == []
    liveness.poke(corpus.id)
    liveness.tick()
    assert backend.scans == [0.0]
    liveness.tick()
    assert len(backend.scans) == 1


def test_poke_after_a_slow_scan_overrides_the_wait(liveness, backend, clock, corpus):
    backend.cost = 1.0
    liveness.watch(corpus.id, corpus, "h")
    clock.now = 3.0
    liveness.tick()
    liveness.poke(corpus.id)
    liveness.tick()
    assert len(backend.scans) == 2


def test_state_before_the_first_scan(liveness, corpus):
    assert liveness.state(corpus.id) is None
    liveness.watch(corpus.id, corpus, "h")
    state = liveness.state(corpus.id)
    assert state["generation"] == 1
    assert state["scanning"] is False
    assert state["last_scan"] is None
    assert state["available"] is True
    assert (state["files"], state["unreadable"], state["unavailable"]) == (3, 1, 1)


def test_state_is_a_copy(liveness, corpus):
    liveness.watch(corpus.id, corpus, "h")
    liveness.state(corpus.id)["generation"] = 99
    assert liveness.state(corpus.id)["generation"] == 1


def test_generation_is_the_backends(liveness, backend, clock, corpus):
    liveness.watch(corpus.id, corpus, "h")
    seen = []
    for step in (3.0, 6.0, 9.0):
        clock.now = step
        backend.finds_change = step == 6.0
        liveness.tick()
        seen.append(liveness.state(corpus.id)["generation"])
    assert seen == [1, 2, 2]
    assert liveness.state(corpus.id)["last_scan"] is not None


def test_counts_follow_the_rows(liveness, backend, clock, corpus, folder):
    liveness.watch(corpus.id, corpus, "h")
    backend.rows = [{"state": "ok"}, {"state": "ok"}, {"state": "unavailable"}]
    clock.now = 3.0
    liveness.tick()
    state = liveness.state(corpus.id)
    assert (state["files"], state["unreadable"], state["unavailable"]) == (3, 0, 1)
    assert state["available"] is True
    folder.rmdir()
    clock.now = 6.0
    liveness.tick()
    assert liveness.state(corpus.id)["available"] is False


def test_a_failing_scan_keeps_the_state(liveness, backend, clock, corpus, caplog):
    liveness.watch(corpus.id, corpus, "h")
    before = liveness.state(corpus.id)
    backend.fail = True
    clock.now = 3.0
    with caplog.at_level(logging.ERROR):
        liveness.tick()
    assert liveness.state(corpus.id) == before
    assert "boom" in caplog.text
    clock.now = 5.9
    liveness.tick()
    assert len(backend.scans) == 1
    clock.now = 6.0
    liveness.tick()
    assert len(backend.scans) == 2


def test_state_answers_while_a_scan_runs(backend, corpus):
    live = Liveness(backend, interval=0.0)
    live.watch(corpus.id, corpus, "h")
    backend.gate = threading.Event()
    ticking = threading.Thread(target=live.tick)
    ticking.start()
    try:
        deadline = time.monotonic() + 3
        while not backend.scans and time.monotonic() < deadline:
            time.sleep(0.01)
        began = time.monotonic()
        state = live.state(corpus.id)
        assert time.monotonic() - began < 0.5
        assert state["scanning"] is True
        live.poke(corpus.id)
    finally:
        backend.gate.set()
        ticking.join(5)
    assert live.state(corpus.id)["scanning"] is False


def test_start_and_stop(corpus):
    backend = ScanBackend()
    live = Liveness(backend, interval=0.05)
    live.stop()
    live.watch(corpus.id, corpus, "h")
    live.start()
    thread = live._thread
    assert thread is not None and thread.is_alive()
    try:
        deadline = time.monotonic() + 1
        while len(backend.scans) < 2 and time.monotonic() < deadline:
            time.sleep(0.02)
        assert len(backend.scans) >= 2
    finally:
        live.stop()
    live.stop()
    assert not thread.is_alive()


# ---- through the server ---------------------------------------------------- #


@pytest.fixture
def served(backend, corpora, liveness):
    server = LibraryServer(backend)
    register_all(server, corpora, liveness=liveness)
    server.start()
    yield server
    server.stop()


def _call(server, method, path, body=None):
    headers = {"Authorization": f"Bearer {server.token}"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    reply = send(server, method, path, headers, data)
    return reply.status, json.loads(reply.body) if reply.body else None


def test_state_route(served, backend, liveness, clock, corpus):
    cid = corpus.id
    assert _call(served, "GET", f"/api/{cid}/state") == (
        200,
        {
            "generation": None,
            "scanning": False,
            "available": True,
            "files": None,
            "unreadable": None,
            "unavailable": None,
            "last_scan": None,
        },
    )
    _call(served, "GET", f"/api/{cid}/files")
    status, data = _call(served, "GET", f"/api/{cid}/state")
    assert status == 200
    assert data["generation"] == 1
    assert data["files"] == 3
    status, _ = _call(served, "POST", f"/api/{cid}/rescan", {})
    assert status == 202
    liveness.tick()
    assert backend.scans == [0.0]
    assert _call(served, "GET", "/api/nope-0000/state") == (
        404,
        {"error": "unknown corpus"},
    )
    assert _call(served, "POST", "/api/nope-0000/rescan", {})[0] == 404


def test_rescan_opens_the_corpus(served, backend, liveness, corpus):
    assert _call(served, "POST", f"/api/{corpus.id}/rescan", {}) == (202, {})
    assert liveness.state(corpus.id) is not None
    liveness.tick()
    assert len(backend.scans) == 1


def test_state_answers_while_files_is_blocked(served, backend, corpus):
    cid = corpus.id
    _call(served, "GET", f"/api/{cid}/state")
    gate = threading.Event()
    real = backend.files
    entered = threading.Event()

    def slow(handle):
        entered.set()
        gate.wait(5)
        return real(handle)

    backend.files = slow
    blocked = threading.Thread(
        target=_call, args=(served, "GET", f"/api/{cid}/files"), daemon=True
    )
    blocked.start()
    try:
        assert entered.wait(3)
        began = time.monotonic()
        status, _ = _call(served, "GET", f"/api/{cid}/state")
        assert status == 200
        assert time.monotonic() - began < 0.5
    finally:
        gate.set()
        blocked.join(5)


def test_library_counts(served, corpus):
    _, before = _call(served, "GET", "/api/library")
    assert before["corpora"][0]["files"] is None
    _call(served, "GET", f"/api/{corpus.id}/files")
    _, after = _call(served, "GET", "/api/library")
    listed = after["corpora"][0]
    assert (listed["files"], listed["unreadable"], listed["unavailable"]) == (3, 1, 1)
