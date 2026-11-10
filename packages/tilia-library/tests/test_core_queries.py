"""The query and statistics panels' routes on CoreBackend, over the test folder.

The folder (``fixtures/corpus``, see its README) holds real ``.tla`` files; the
core indexes it in memory, so the tests open it in place.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from conftest import send

from tilia_core import tql
from tilia_library.api import register_all
from tilia_library.backend import CoreBackend
from tilia_library.corpora import Corpora
from tilia_library.server import LibraryServer

FOLDER = Path(__file__).resolve().parent / "fixtures" / "corpus"
SEQUENCE = "Exposição THEN Development"
OLD_FILES = {"0.0.96.tla", "0.5.15.tla", "0.7.0.tla"}
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
    listed = Corpora(tmp_path / "library.toml")
    listed.add(FOLDER)
    return listed


@pytest.fixture
def cid(corpora):
    return corpora.all()[0].id


@pytest.fixture
def core(corpora):
    server = LibraryServer(CoreBackend())
    register_all(server, corpora)
    server.start()
    yield server
    server.stop()


@pytest.fixture
def handle():
    return CoreBackend().open_corpus(FOLDER)


def _ql(server, cid, **body):
    body.setdefault("query", SEQUENCE)
    body.setdefault("limit", None)
    body.setdefault("tab", "t1")
    return _call(server, "POST", f"/api/{cid}/ql", body)


def _stats(server, cid, **body):
    body.setdefault("query", "* IN hierarchies")
    body.setdefault("by", ["label"])
    body.setdefault("tab", "t1")
    return _call(server, "POST", f"/api/{cid}/statistics", body)


def _run(handle, text, *, max_matches=100, cancel=None):
    return CoreBackend().run(
        handle,
        text,
        max_matches=max_matches,
        time_limit=30.0,
        cancel=cancel or threading.Event(),
    )


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #
def test_a_sequence_fills_the_cards(core, cid):
    status, body = _ql(core, cid)
    assert status == 200
    assert RUN_KEYS <= set(body)
    rows, matches = body["rows"], body["matches"]
    assert body["count"] == body["total"] == len(rows) == len(matches) == 3
    assert body["truncated"] is False
    assert body["stopped"] is None
    assert body["files"] == 3
    assert body["slots"] == 2
    assert body["explain"] == tql.explain(tql.parse(SEQUENCE))
    assert body["action"] is None and body["action_error"] is None
    assert any("unreadable" in warning for warning in body["warnings"])
    assert {m["name"] for m in matches} == OLD_FILES
    for row, match in zip(rows, matches, strict=True):
        assert set(row) == set(body["columns"])
        assert row["file"] == match["name"]
        assert row["$1.label"] == "Exposição"
        assert row["$2.label"] == "Development"
        labels = [[unit["label"] for unit in slot] for slot in match["slots"]]
        assert labels == [["Exposição"], ["Development"]]
        assert match["start"] <= match["match_start"] < match["match_end"]
        assert match["match_end"] <= match["end"]
        assert match["lane"]["kind"] == "hierarchy"
        assert match["timelines"] == [match["lane"]["timeline_id"]]
        assert all(isinstance(match[k], str) for k in ("key", "file_id"))


def test_limit_cuts_the_answer(core, cid):
    status, body = _ql(core, cid, limit=1)
    assert status == 200
    assert (body["count"], body["total"], body["truncated"]) == (1, 3, True)


def test_error_positions_are_code_points(core, cid):
    status, body = _ql(core, cid, query="🎵 error")
    assert status == 400
    assert (body["pos"], body["end"]) == (2, 7)
    assert body["error"] and body["detail"]


def test_an_action_is_refused_where_it_is_written(core, cid):
    text = '* IN hierarchies -> TAG "x"'
    status, body = _ql(core, cid, query=text)
    assert status == 200
    assert body["action"] == "tag"
    assert body["action_error"] == {
        "error": "bulk edits are not available yet",
        "pos": text.index("->"),
        "end": len(text),
    }


def test_a_cancelled_run_says_so(handle):
    cancel = threading.Event()
    cancel.set()
    assert _run(handle, "* THEN *", cancel=cancel)["stopped"] == "cancelled"


def test_a_run_stops_at_max_matches(handle):
    result = _run(handle, "* IN hierarchies", max_matches=2)
    assert result["stopped"] == "max_matches"
    assert len(result["rows"]) == 2


def test_answers_carry_the_index_generation(core, cid, handle):
    _, ql = _ql(core, cid)
    _, sql = _call(core, "POST", f"/api/{cid}/sql", {"sql": "SELECT 1", "tab": "t"})
    _, stats = _stats(core, cid)
    generation = CoreBackend().generation(handle)
    assert ql["generation"] == sql["generation"] == stats["generation"] == generation


# --------------------------------------------------------------------------- #
# SQL
# --------------------------------------------------------------------------- #
def test_show_sql(core, cid):
    status, body = _call(core, "POST", f"/api/{cid}/ql-sql", {"query": SEQUENCE})
    assert status == 200
    assert set(body) == {"sql", "notes"}
    assert "SELECT" in body["sql"].upper()
    status, body = _call(core, "POST", f"/api/{cid}/ql-sql", {"query": "🎵 error"})
    assert (status, body["pos"], body["end"]) == (400, 2, 7)


def test_sql_reads_the_index(core, cid):
    status, body = _call(
        core,
        "POST",
        f"/api/{cid}/sql",
        {"sql": "SELECT count(*) AS n FROM files", "tab": "t1"},
    )
    assert status == 200
    assert body["columns"] == ["n"]
    assert body["rows"] == [[5]]
    assert body["stopped"] is None


def test_sql_refusals(core, cid):
    for sql in ("DROP TABLE files", "SELECT nope"):
        status, body = _call(core, "POST", f"/api/{cid}/sql", {"sql": sql, "tab": "t"})
        assert status == 400, sql
        assert body["error"], sql


def test_a_cancelled_sql_says_so(handle):
    cancel = threading.Event()
    cancel.set()
    result = CoreBackend().sql(
        handle, "SELECT * FROM components", max_rows=10, time_limit=5.0, cancel=cancel
    )
    assert result["stopped"] == "cancelled"


# --------------------------------------------------------------------------- #
# The cards' strips
# --------------------------------------------------------------------------- #
def _a_match(core, cid):
    _, body = _ql(core, cid)
    return next(m for m in body["matches"] if m["name"] == "0.7.0.tla")


def test_context_draws_the_strips(core, cid):
    match = _a_match(core, cid)
    status, body = _call(core, "GET", f"/api/{cid}/ql-context/{match['file_id']}")
    assert status == 200
    assert (body["file_id"], body["name"]) == (match["file_id"], "0.7.0.tla")
    assert isinstance(body["end"], float)
    kinds = [t["kind"] for t in body["timelines"]]
    assert set(kinds) == {"hierarchy", "marker", "harmony", "range"}
    for timeline in body["timelines"]:
        assert timeline["rows"]
        for unit in timeline["components"]:
            assert str(unit["level"]) in timeline["rows"]
            assert unit["point"] == (unit["start"] == unit["end"])
    form = next(t for t in body["timelines"] if t["kind"] == "hierarchy")
    labels = {unit["label"] for unit in form["components"]}
    assert {"Exposição", "Development"} <= labels


def test_context_of_named_timelines(core, cid):
    match = _a_match(core, cid)
    lane = match["lane"]["timeline_id"]
    path = f"/api/{cid}/ql-context/{match['file_id']}?tl={lane}"
    status, body = _call(core, "GET", path)
    assert status == 200
    assert [t["id"] for t in body["timelines"]] == [lane]


@pytest.mark.parametrize("file_id", ["999999", "nope"])
def test_context_of_an_unknown_file(core, cid, file_id):
    status, body = _call(core, "GET", f"/api/{cid}/ql-context/{file_id}")
    assert (status, body) == (404, {"error": "unknown file"})


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #
def _tables(body):
    return {t["name"]: t for t in body["tables"]}


def test_one_key_gives_four_tables(core, cid):
    status, body = _stats(core, cid)
    assert status == 200
    assert [t["name"] for t in body["tables"]] == NAMES
    tables = _tables(body)
    assert tables["counts"]["columns"] == ["label", "matches", "files"]
    assert tables["durations"]["columns"][:2] == ["label", "n"]
    assert tables["positions"]["columns"] == ["label", "from_pct", "to_pct", "n"]
    assert tables["transitions"]["columns"] == ["from", "to", "n"]
    for table in body["tables"]:
        assert table["rows"], table["name"]
        assert all(len(row) == len(table["columns"]) for row in table["rows"])
    assert tables["counts"]["chart"]["x"] == "label"
    assert ["Exposição", "Development", 3] in tables["transitions"]["rows"]


def test_labels_in_several_scripts_survive(core, cid):
    _, body = _stats(core, cid)
    labels = {row[0] for row in _tables(body)["counts"]["rows"]}
    assert {"Exposição", "Hauptsatz – Überleitung", "Θέμα β", "主題", "נושא"} <= labels


def test_two_keys_cross_tabulate(core, cid):
    status, body = _stats(core, cid, by=["label", "file"])
    assert status == 200
    counts = _tables(body)["counts"]
    assert counts["columns"] == ["label", "file", "matches", "files"]
    assert counts["chart"]["series"] == "file"


def test_fold_runs(core, cid):
    status, body = _stats(core, cid, fold=True)
    assert status == 200
    assert [t["name"] for t in body["tables"]] == NAMES


def test_statistics_errors(core, cid):
    status, body = _stats(core, cid, query="a error b")
    assert (status, body["pos"], body["end"]) == (400, 2, 7)
    status, body = _stats(core, cid, by=["no such key"])
    assert status == 400
    assert body["error"]
