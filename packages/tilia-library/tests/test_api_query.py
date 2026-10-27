from __future__ import annotations

import json
import threading
import time

import pytest
from conftest import send
from support.fixture_backend import FixtureBackend

from tilia_library.api import register_all
from tilia_library.backend import CoreBackend
from tilia_library.corpora import Corpora
from tilia_library.server import LibraryServer

RUN_KEYS = {
    "columns",
    "rows",
    "matches",
    "files",
    "grain",
    "slots",
    "target",
    "explain",
    "warnings",
    "action",
    "action_error",
    "stopped",
    "generation",
    "count",
    "total",
    "truncated",
}


def _call(server, method, path, body=None):
    headers = {"Authorization": f"Bearer {server.token}"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    reply = send(server, method, path, headers, data)
    return reply.status, (json.loads(reply.body) if reply.body else None)


@pytest.fixture
def corpora(tmp_path):
    folder = tmp_path / "pieces"
    folder.mkdir()
    listed = Corpora(tmp_path / "library.toml")
    listed.add(folder)
    return listed


@pytest.fixture
def cid(corpora):
    return corpora.all()[0].id


def _serve(backend, corpora):
    server = LibraryServer(backend)
    register_all(server, corpora)
    server.start()
    return server


@pytest.fixture
def library(corpora):
    server = _serve(FixtureBackend(), corpora)
    yield server
    server.stop()


def _ql(library, cid, **body):
    body.setdefault("query", "a then b")
    body.setdefault("limit", None)
    body.setdefault("tab", "t1")
    return _call(library, "POST", f"/api/{cid}/ql", body)


def test_ql_answers_with_the_run_shape(library, cid):
    status, body = _ql(library, cid)
    assert status == 200
    assert RUN_KEYS <= set(body)
    assert body["count"] == body["total"] == len(body["rows"]) == len(body["matches"])
    assert body["count"] >= 3
    assert body["truncated"] is False
    assert body["stopped"] is None


def test_ql_limit_cuts_rows_and_matches(library, cid):
    _, full = _ql(library, cid)
    status, body = _ql(library, cid, limit=1)
    assert status == 200
    assert len(body["rows"]) == len(body["matches"]) == body["count"] == 1
    assert body["total"] == full["total"]
    assert body["truncated"] is True
    assert body["rows"][0] == full["rows"][0]


@pytest.mark.parametrize(
    "body",
    [
        {"query": "", "limit": None, "tab": "t1"},
        {"query": "  \n\t", "limit": None, "tab": "t1"},
        {"query": 5, "limit": None, "tab": "t1"},
        {"query": "q", "limit": -1, "tab": "t1"},
        {"query": "q", "limit": "x", "tab": "t1"},
        {"query": "q", "limit": None},
        {"query": "q", "limit": None, "tab": ""},
    ],
)
def test_ql_refuses_bad_requests(library, cid, body):
    status, answer = _call(library, "POST", f"/api/{cid}/ql", body)
    assert status == 400
    assert answer["error"]


def test_ql_empty_query_message(library, cid):
    _, answer = _ql(library, cid, query="   ")
    assert answer["error"] == "empty query"


def test_ql_error_positions_are_code_points(library, cid):
    status, answer = _ql(library, cid, query="🎵 error")
    assert status == 400
    assert (answer["pos"], answer["end"]) == (2, 7)
    assert answer["error"] and answer["detail"]


def test_text_reaches_the_seam_as_typed(corpora, cid):
    seen = []

    class Recording(FixtureBackend):
        def run(self, corpus, text, **kwargs):
            seen.append(text)
            return super().run(corpus, text, **kwargs)

    server = _serve(Recording(), corpora)
    try:
        typed = "  Überleitunǵ  → x "
        status, _ = _ql(server, cid, query=typed)
        assert status == 200
        assert seen == [typed]
    finally:
        server.stop()


class WaitingBackend(FixtureBackend):
    """A backend whose run and sql wait for their cancel event."""

    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Semaphore(0)

    def run(self, corpus, text, *, max_matches, time_limit, cancel):
        self.started.release()
        cancel.wait(5)
        return super().run(
            corpus,
            text,
            max_matches=max_matches,
            time_limit=time_limit,
            cancel=cancel,
        )


def _in_thread(server, cid, tab, results):
    def go():
        results[tab] = _ql(server, cid, tab=tab)

    thread = threading.Thread(target=go)
    thread.start()
    return thread


@pytest.fixture
def waiting(corpora):
    backend = WaitingBackend()
    server = _serve(backend, corpora)
    yield server, backend
    server.stop()


def test_a_new_run_from_the_same_tab_cancels_the_old_one(waiting, cid):
    server, backend = waiting
    results = {}
    first = _in_thread(server, cid, "t1", results)
    assert backend.started.acquire(timeout=5)
    second = _in_thread(server, cid, "t1", {})
    first.join(5)
    assert results["t1"][0] == 200
    assert results["t1"][1]["stopped"] == "cancelled"
    # let the second one finish so the thread ends
    assert backend.started.acquire(timeout=5)
    assert _call(server, "POST", f"/api/{cid}/ql-stop", {"tab": "t1"})[0] == 204
    second.join(5)


def test_ql_stop_stops_that_tab_only(waiting, cid):
    server, backend = waiting
    results = {}
    one = _in_thread(server, cid, "t1", results)
    two = _in_thread(server, cid, "t2", results)
    assert backend.started.acquire(timeout=5)
    assert backend.started.acquire(timeout=5)
    started = time.monotonic()
    assert _call(server, "POST", f"/api/{cid}/ql-stop", {"tab": "t2"})[0] == 204
    two.join(5)
    assert results["t2"][1]["stopped"] == "cancelled"
    assert "t1" not in results
    assert _call(server, "POST", f"/api/{cid}/ql-stop", {"tab": "t1"})[0] == 204
    one.join(5)
    assert results["t1"][1]["stopped"] == "cancelled"
    assert time.monotonic() - started < 4


def test_ql_stop_of_an_idle_tab(library, cid):
    status, body = _call(library, "POST", f"/api/{cid}/ql-stop", {"tab": "idle"})
    assert status == 204
    assert body is None


def test_ql_sql(library, cid):
    status, body = _call(library, "POST", f"/api/{cid}/ql-sql", {"query": "a"})
    assert status == 200
    assert set(body) == {"sql", "notes"}
    status, body = _call(library, "POST", f"/api/{cid}/ql-sql", {"query": "🎵 error"})
    assert status == 400
    assert (body["pos"], body["end"]) == (2, 7)


def test_sql(library, cid):
    status, body = _call(
        library, "POST", f"/api/{cid}/sql", {"sql": "SELECT 1", "tab": "t1"}
    )
    assert status == 200
    assert set(body) == {"columns", "rows", "stopped", "generation"}
    assert body["stopped"] is None


def test_sql_refusals(library, cid):
    status, body = _call(
        library, "POST", f"/api/{cid}/sql", {"sql": "DROP TABLE x", "tab": "t1"}
    )
    assert status == 400
    assert body["error"] == "only SELECT statements can run here"
    status, body = _call(library, "POST", f"/api/{cid}/sql", {"sql": " ", "tab": "t1"})
    assert status == 400
    assert body["error"] == "empty SQL"


def test_ql_context(library, cid):
    status, body = _call(library, "GET", f"/api/{cid}/ql-context/f1?tl=t2")
    assert status == 200
    assert [t["id"] for t in body["timelines"]] == ["t2"]
    status, body = _call(library, "GET", f"/api/{cid}/ql-context/f1")
    assert [t["id"] for t in body["timelines"]] == ["t1", "t2", "t3"]
    status, body = _call(library, "GET", f"/api/{cid}/ql-context/f1?tl=")
    assert len(body["timelines"]) == 3
    status, body = _call(library, "GET", f"/api/{cid}/ql-context/f1?tl=t1,t3")
    assert [t["id"] for t in body["timelines"]] == ["t1", "t3"]
    status, body = _call(library, "GET", f"/api/{cid}/ql-context/nope")
    assert (status, body) == (404, {"error": "unknown file"})


def test_context_fixture_has_colors_and_points(library, cid):
    _, body = _call(library, "GET", f"/api/{cid}/ql-context/f1")
    components = [c for t in body["timelines"] for c in t["components"]]
    assert all(c["color"].startswith("#") and len(c["color"]) == 7 for c in components)
    assert any(c["point"] for c in components)


def test_unknown_corpus(library):
    for method, path, body in [
        ("POST", "/api/nope/ql", {"query": "q", "limit": None, "tab": "t"}),
        ("POST", "/api/nope/ql-stop", {"tab": "t"}),
        ("POST", "/api/nope/ql-sql", {"query": "q"}),
        ("POST", "/api/nope/sql", {"sql": "select 1", "tab": "t"}),
        ("GET", "/api/nope/ql-context/f1", None),
    ]:
        status, answer = _call(library, method, path, body)
        assert status == 404, path
        assert answer == {"error": "unknown corpus"}


def test_core_backend_says_not_available(corpora, cid):
    server = _serve(CoreBackend(), corpora)
    try:
        status, body = _ql(server, cid)
        assert status == 501
        assert body["error"] == "not available yet"
        assert body["needs"] in ("the query engine", "the index")
    finally:
        server.stop()
