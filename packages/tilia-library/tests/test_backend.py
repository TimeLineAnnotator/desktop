from __future__ import annotations

import builtins
import json
import logging
import pathlib
import threading
from pathlib import Path

import pytest
from conftest import send
from support.fixture_backend import FixtureBackend

from tilia_library.backend import Backend, CoreBackend, NotAvailable, QueryError
from tilia_library.server import ApiError, LibraryServer

SUPPORT = Path(__file__).resolve().parent / "support"
CORPUS = Path("corpus")


def method_names():
    return [
        n for n, v in vars(Backend).items() if callable(v) and not n.startswith("_")
    ]


def call(backend, name, cancel=None):
    """Call a backend method with plausible arguments."""
    cancel = cancel or threading.Event()
    corpus = backend.open_corpus(CORPUS) if name != "open_corpus" else None
    args = {
        "open_corpus": (CORPUS,),
        "generation": (corpus,),
        "scan": (corpus,),
        "reread": (corpus, CORPUS / "a.tla"),
        "files": (corpus,),
        "file_detail": (corpus, "f1"),
        "context": (corpus, "f1", []),
        "explain": ("hello",),
        "query_sql": (corpus, "hello"),
        "categories": (corpus, True),
        "plan": (corpus, "rename", set()),
        "apply": (corpus, {"plan": []}, {"k1"}, set()),
        "edit_log": (corpus,),
        "undo": (corpus, "e1", set()),
        "media_of": (corpus, "f1"),
    }
    kwargs = {
        "run": ((corpus, "hello"), dict(max_matches=10, time_limit=1.0, cancel=cancel)),
        "statistics": ((corpus, "hello", ["label"]), dict(fold=False)),
        "sql": ((corpus, "select 1"), dict(max_rows=10, time_limit=1.0, cancel=cancel)),
    }
    if name in kwargs:
        a, k = kwargs[name]
        return getattr(backend, name)(*a, **k)
    return getattr(backend, name)(*args[name])


def test_protocol_methods_exist_on_both():
    names = method_names()
    assert len(names) >= 18
    for name in names:
        assert callable(getattr(CoreBackend, name)), name
        assert callable(getattr(FixtureBackend, name)), name


@pytest.mark.parametrize("name", method_names())
def test_core_backend_not_available(name):
    with pytest.raises(NotAvailable) as info:
        call(CoreBackend(), name)
    assert info.value.needs


def test_core_backend_needs_texts():
    core = CoreBackend()
    assert pytest.raises(NotAvailable, core.scan, None).value.needs == "the index"
    assert (
        pytest.raises(NotAvailable, core.explain, "x").value.needs == "the query engine"
    )
    assert (
        pytest.raises(NotAvailable, core.plan, None, "x", set()).value.needs
        == "bulk edits"
    )
    assert pytest.raises(NotAvailable, core.media_of, None, "f").value.needs == "media"


def test_route_with_core_backend_is_501():
    core = CoreBackend()
    with LibraryServer(core) as srv:
        srv.router.add(
            "GET",
            "/api/files",
            lambda r: __import__("tilia_library.server", fromlist=["x"]).json_response(
                r.server.backend.files(None)
            ),
        )
        r = send(srv, "GET", "/api/files", {"Authorization": f"Bearer {srv.token}"})
    assert r.status == 501
    assert json.loads(r.body) == {"error": "not available yet", "needs": "the index"}


def test_api_error_and_internal_error(server, caplog):
    def not_found(request):
        raise ApiError(404, "unknown corpus")

    def broken(request):
        raise RuntimeError("boom")

    server.router.add("GET", "/api/nf", not_found)
    server.router.add("GET", "/api/broken/{x}", broken)
    h = {"Authorization": f"Bearer {server.token}"}
    r = send(server, "GET", "/api/nf", h)
    assert r.status == 404
    assert json.loads(r.body) == {"error": "unknown corpus"}
    with caplog.at_level(logging.ERROR):
        r = send(server, "GET", "/api/broken/1", h)
    assert r.status == 500
    assert json.loads(r.body) == {"error": "internal error"}
    record = next(r for r in caplog.records if r.exc_info)
    assert "/api/broken/{x}" in record.getMessage()
    assert "boom" in "".join(__import__("traceback").format_exception(*record.exc_info))
    assert server.token not in record.getMessage()


@pytest.mark.parametrize("name", method_names())
def test_fixture_backend_shapes_are_json(name):
    result = call(FixtureBackend(), name)
    if name != "open_corpus":
        json.dumps(result)


def keys(d):
    return set(d)


def test_fixture_shapes():
    b = FixtureBackend()
    corpus = b.open_corpus(Path("/x/corpus"))
    assert corpus == "corpus"
    assert keys(b.scan(corpus)) == {
        "changed",
        "added",
        "removed",
        "unreadable",
        "unavailable",
    }
    assert set(b.reread(corpus, Path("a.tla"))) == keys(b.scan(corpus))
    files = b.files(corpus)
    assert [f["state"] for f in files] == ["ok", "ok", "unreadable", "unavailable"]
    assert files[2]["reason"].startswith("line 12")
    for f in files:
        assert keys(f) == {
            "file_id",
            "name",
            "path",
            "state",
            "reason",
            "fields",
            "timelines",
        }
        assert keys(f["timelines"]) == {"count", "kinds"}
    detail = b.file_detail(corpus, "f1")
    assert keys(detail) == {"file_id", "name", "path", "fields", "timelines"}
    assert keys(detail["timelines"][0]) == {"id", "name", "kind", "fields"}
    ctx = b.context(corpus, "f1", [])
    assert keys(ctx) == {"file_id", "name", "end", "timelines"}
    assert keys(ctx["timelines"][0]["components"][0]) == {
        "component_id",
        "level",
        "start",
        "end",
        "label",
        "color",
        "point",
    }
    assert [t["id"] for t in b.context(corpus, "f1", ["t2"])["timelines"]] == ["t2"]
    labels = {u["label"] for t in ctx["timelines"] for u in t["components"]}
    assert {"Überleitung", "transição", "μετάβαση", "过渡", "מעבר", "🎵"} <= labels
    ev = threading.Event()
    run = b.run(corpus, "q", max_matches=5, time_limit=1, cancel=ev)
    assert keys(run) == {
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
    }
    assert run["stopped"] is None
    assert keys(run["matches"][0]) == {
        "key",
        "file_id",
        "name",
        "start",
        "end",
        "match_start",
        "match_end",
        "lane",
        "slots",
        "timelines",
    }
    assert keys(b.query_sql(corpus, "q")) == {"sql", "notes"}
    sql = b.sql(corpus, "select 1", max_rows=5, time_limit=1, cancel=ev)
    assert keys(sql) == {"columns", "rows", "stopped", "generation"}
    stats = b.statistics(corpus, "q", ["label"], fold=False)
    assert keys(stats) == {"generation", "tables", "warnings"}
    assert keys(stats["tables"][0]) == {"name", "title", "columns", "rows"}
    cats = b.categories(corpus, False)
    assert keys(cats) == {"generation", "categories"}
    assert keys(cats["categories"][0]) == {"category", "group", "n"}
    plan = b.plan(corpus, "s", set())
    assert keys(plan) == {
        "plan",
        "skipped_files",
        "summary",
        "explain",
        "warnings",
        "generation",
    }
    assert keys(plan["plan"][0]) == {
        "key",
        "file_id",
        "name",
        "do",
        "reason",
        "writes",
    }
    assert keys(plan["plan"][0]["writes"][0]) == {
        "op",
        "component_id",
        "timeline_id",
        "field",
        "old",
        "new",
    }
    assert keys(b.apply(corpus, plan, {"k1"}, set())) == {
        "written",
        "skipped",
        "entry",
        "generation",
    }
    log = b.edit_log(corpus)
    assert keys(log[0]) == {"entry", "statement", "at", "files", "undone"}
    assert keys(b.undo(corpus, "e1", set())) == {
        "restored",
        "refused",
        "skipped",
        "generation",
    }
    for fid, kind in [("f1", "local"), ("f2", "none"), ("f3", "youtube")]:
        m = b.media_of(corpus, fid)
        assert keys(m) == {"kind", "path", "youtube_id", "length", "reason"}
        assert m["kind"] == kind
    assert isinstance(b.generation(corpus), int)


def test_fixture_returns_copies():
    b = FixtureBackend()
    b.files("c")[0]["name"] = "changed"
    assert b.files("c")[0]["name"] != "changed"


def test_unknown_file_id():
    b = FixtureBackend()
    for fn in (b.file_detail, b.media_of):
        with pytest.raises(KeyError):
            fn("c", "nope")
    with pytest.raises(KeyError):
        b.context("c", "nope", [])


def test_cancel_honoured():
    b = FixtureBackend()
    ev = threading.Event()
    ev.set()
    assert call(b, "run", ev)["stopped"] == "cancelled"
    assert call(b, "sql", ev)["stopped"] == "cancelled"


def test_query_error_positions():
    b = FixtureBackend()
    with pytest.raises(QueryError) as info:
        b.explain("a bad error here")
    assert info.value.pos == 6
    assert info.value.end == 11
    assert info.value.msg
    assert isinstance(b.explain("fine"), str)


def test_never_opens_tla(monkeypatch):
    real_open = builtins.open
    real_path_open = pathlib.Path.open

    def guard(target):
        if str(target).endswith(".tla"):
            raise AssertionError(f"opened {target}")

    def fake_open(file, *a, **k):
        guard(file)
        return real_open(file, *a, **k)

    def fake_path_open(self, *a, **k):
        guard(self)
        return real_path_open(self, *a, **k)

    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(pathlib.Path, "open", fake_path_open)
    b = FixtureBackend()
    for name in method_names():
        call(b, name)
    assert not list(SUPPORT.rglob("*.tla"))
