from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import send
from support.fixture_backend import FixtureBackend

import tilia_library
from tilia_library.api import register_all
from tilia_library.backend import CoreBackend
from tilia_library.corpora import Corpora
from tilia_library.server import LibraryServer

VENDOR = Path(tilia_library.__file__).resolve().parent / "web/vendor/chart.js"
NAMES = ["counts", "durations", "positions", "transitions"]


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


def _stats(library, cid, **body):
    body.setdefault("query", "a then b")
    body.setdefault("by", ["label"])
    body.setdefault("tab", "t1")
    return _call(library, "POST", f"/api/{cid}/statistics", body)


def _tables(body):
    return {t["name"]: t for t in body["tables"]}


def test_one_key_gives_four_tables_with_charts(library, cid):
    status, body = _stats(library, cid, by=["category"])
    assert status == 200
    assert [t["name"] for t in body["tables"]] == NAMES
    assert "generation" in body and body["warnings"] == []
    tables = _tables(body)
    assert tables["counts"]["columns"] == ["category", "matches", "files"]
    assert tables["counts"]["chart"] == {
        "kind": "bar",
        "x": "category",
        "y": "matches",
        "series": None,
    }
    assert tables["durations"]["columns"][0] == "category"
    assert tables["durations"]["chart"] == {
        "kind": "bar",
        "x": "category",
        "y": "median",
        "series": None,
    }
    assert tables["positions"]["columns"] == ["category", "from_pct", "to_pct", "n"]
    assert tables["positions"]["chart"] == {
        "kind": "bar",
        "x": "from_pct",
        "y": "n",
        "series": "category",
    }
    assert tables["transitions"]["columns"] == ["from", "to", "n"]
    assert tables["transitions"]["chart"] is None
    for table in body["tables"]:
        assert all(len(row) == len(table["columns"]) for row in table["rows"])


def test_two_keys_cross_tabulate(library, cid):
    status, body = _stats(library, cid, by=["category", "file"])
    assert status == 200
    tables = _tables(body)
    assert tables["counts"]["columns"] == ["category", "file", "matches", "files"]
    assert tables["counts"]["chart"]["series"] == "file"
    assert tables["counts"]["chart"]["x"] == "category"
    assert tables["durations"]["columns"][0] == "category"
    assert tables["positions"]["chart"]["series"] == "category"
    assert tables["positions"]["columns"][0] == "category"


def test_fold_reaches_the_backend(library, cid):
    _, plain = _stats(library, cid)
    assert plain["warnings"] == []
    status, body = _stats(library, cid, fold=True)
    assert status == 200
    assert "subtypes folded" in body["warnings"]
    status, body = _stats(library, cid, fold=False)
    assert status == 200 and body["warnings"] == []


@pytest.mark.parametrize("fold", ["yes", 1, None, []])
def test_fold_must_be_a_bool(library, cid, fold):
    status, body = _stats(library, cid, fold=fold)
    assert status == 400 and "fold" in body["error"]


@pytest.mark.parametrize("query", ["", "  \n", None, 3])
def test_empty_query(library, cid, query):
    status, body = _stats(library, cid, query=query)
    assert (status, body["error"]) == (400, "empty query")


@pytest.mark.parametrize(
    "by", [[], ["a", "b", "c"], [3], ["label", ""], "label", None, ["label", 2], [""]]
)
def test_by_must_name_one_or_two_keys(library, cid, by):
    status, body = _stats(library, cid, by=by)
    assert (status, body["error"]) == (400, "by must name one or two keys")


def test_missing_by_and_tab(library, cid):
    status, body = _call(
        library, "POST", f"/api/{cid}/statistics", {"query": "q", "tab": "t"}
    )
    assert (status, body["error"]) == (400, "by must name one or two keys")
    status, body = _call(
        library, "POST", f"/api/{cid}/statistics", {"query": "q", "by": ["label"]}
    )
    assert (status, body["error"]) == (400, "missing tab")


def test_query_error_is_400_with_position(library, cid):
    status, body = _stats(library, cid, query="a error b")
    assert status == 400
    assert (body["pos"], body["end"]) == (2, 7)
    assert body["error"] and "detail" in body


def test_unknown_corpus(library):
    status, _ = _stats(library, "nope")
    assert status == 404


def test_core_backend_is_501(corpora, cid):
    server = _serve(CoreBackend(), corpora)
    try:
        status, body = _stats(server, cid)
    finally:
        server.stop()
    assert status == 501
    assert body["needs"] in ("the query engine", "the index")


def test_labels_in_several_scripts_survive(library, cid):
    _, body = _stats(library, cid)
    labels = {row[0] for row in _tables(body)["counts"]["rows"]}
    assert {"Überleitung", "μετάβαση", "过渡", "מעבר", "🎵"} <= labels


def test_vendored_chart_js(library):
    script = VENDOR / "chart.umd.js"
    assert script.read_text(encoding="utf-8").startswith("/*!\n * Chart.js v4.4.4\n")
    assert "The MIT License (MIT)" in (VENDOR / "LICENSE.md").read_text(
        encoding="utf-8"
    )
    headers = {"Authorization": f"Bearer {library.token}"}
    reply = send(library, "GET", "/web/vendor/chart.js/chart.umd.js", headers)
    assert reply.status == 200
    assert reply.headers["content-type"].startswith("text/javascript")
    assert reply.body == script.read_bytes()
