"""The files panel and the rescans on CoreBackend, over a copy of the test folder.

The tests change the folder (remove, add and break files), so each works on
its own copy of ``fixtures/corpus`` (see its README). Liveness runs on a fake
clock and rescans when a test ticks it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from conftest import send

from tilia_library.api import register_all
from tilia_library.backend import CoreBackend
from tilia_library.corpora import Corpora
from tilia_library.liveness import Liveness
from tilia_library.server import LibraryServer

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "corpus"
NAMES = ["0.0.96.tla", "0.5.15.tla", "0.7.0.tla", "every-kind.tla", "not-json.tla"]


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _call(server, method, path, body=None):
    headers = {"Authorization": f"Bearer {server.token}"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    reply = send(server, method, path, headers, data)
    return reply.status, (json.loads(reply.body) if reply.body else None)


@pytest.fixture
def folder(tmp_path):
    copy = tmp_path / "pieces"
    shutil.copytree(FIXTURES, copy, ignore=shutil.ignore_patterns("*.md"))
    return copy


@pytest.fixture
def corpora(tmp_path, folder):
    listed = Corpora(tmp_path / "library.toml")
    listed.add(folder)
    return listed


@pytest.fixture
def cid(corpora):
    return corpora.all()[0].id


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def liveness(clock):
    return Liveness(CoreBackend(), clock=clock)


@pytest.fixture
def core(corpora, liveness):
    server = LibraryServer(liveness._backend)
    register_all(server, corpora, liveness=liveness)
    server.start()
    yield server
    server.stop()


def _files(core, cid):
    status, body = _call(core, "GET", f"/api/{cid}/files")
    assert status == 200
    return body


def _row(body, name):
    return next(row for row in body["rows"] if row["name"] == name)


def _rescan(liveness, clock, cid):
    liveness.poke(cid)
    liveness.tick()
    clock.now += 1.0


# --------------------------------------------------------------------------- #
# The files panel
# --------------------------------------------------------------------------- #
def test_files_lists_the_folder(core, cid):
    body = _files(core, cid)
    assert body["available"] is True
    assert isinstance(body["generation"], int)
    assert [row["name"] for row in body["rows"]] == NAMES
    states = {row["name"]: row["state"] for row in body["rows"]}
    assert states == {name: "ok" for name in NAMES[:4]} | {"not-json.tla": "unreadable"}
    for row in body["rows"]:
        assert set(row) == {
            "file_id",
            "name",
            "path",
            "state",
            "reason",
            "fields",
            "timelines",
        }
        assert row["path"] == row["name"]
    every = _row(body, "every-kind.tla")
    assert every["reason"] is None
    assert every["fields"]["composer"] == "Franz Schubert"
    assert every["fields"]["genre"] == ["Lied", "romantic"]
    assert every["timelines"]["kinds"]["beat"] == 2
    assert every["timelines"]["count"] == sum(every["timelines"]["kinds"].values())
    assert set(every["timelines"]["kinds"]) == {
        "slider",
        "beat",
        "hierarchy",
        "marker",
        "harmony",
        "range",
        "score",
        "pdf",
        "audiowave",
    }


def test_an_unreadable_file_says_where(core, cid):
    row = _row(_files(core, cid), "not-json.tla")
    assert row["reason"].startswith("can't read (line 2)")
    assert row["timelines"] == {"count": 0, "kinds": {}}


def test_file_detail(core, cid):
    every = _row(_files(core, cid), "every-kind.tla")
    status, body = _call(core, "GET", f"/api/{cid}/files/{every['file_id']}")
    assert status == 200
    assert (body["file_id"], body["name"]) == (every["file_id"], "every-kind.tla")
    assert body["fields"]["performer"] == "内田光子"
    assert isinstance(body["generation"], int)
    kinds = [t["kind"] for t in body["timelines"]]
    assert sorted(kinds) == sorted(
        k for k, n in every["timelines"]["kinds"].items() for _ in range(n)
    )
    form = next(t for t in body["timelines"] if t["kind"] == "hierarchy")
    assert form["fields"]["units"] > 0
    assert form["fields"]["levels"] >= 1
    assert all(isinstance(t["id"], str) for t in body["timelines"])


@pytest.mark.parametrize("file_id", ["999999", "nope"])
def test_unknown_file(core, cid, file_id):
    status, body = _call(core, "GET", f"/api/{cid}/files/{file_id}")
    assert (status, body) == (404, {"error": "unknown file"})


def test_library_counts(core, cid):
    _files(core, cid)
    _, body = _call(core, "GET", "/api/library")
    listed = body["corpora"][0]
    assert (listed["files"], listed["unreadable"], listed["unavailable"]) == (5, 1, 0)


# --------------------------------------------------------------------------- #
# A missing folder (T1)
# --------------------------------------------------------------------------- #
def test_a_folder_missing_from_the_start_is_unavailable(core, cid, folder):
    shutil.rmtree(folder)
    body = _files(core, cid)
    assert (body["available"], body["rows"]) == (False, [])
    status, answer = _call(
        core, "POST", f"/api/{cid}/ql", {"query": "*", "limit": None, "tab": "t"}
    )
    assert status == 400 and answer["error"] == "the corpus folder is missing"
    status, answer = _call(
        core, "POST", f"/api/{cid}/sql", {"sql": "SELECT 1", "tab": "t"}
    )
    assert status == 400 and answer["error"] == "the corpus folder is missing"
    assert _call(core, "GET", f"/api/{cid}/files/1")[0] == 404
    assert _call(core, "GET", f"/api/{cid}/ql-context/1")[0] == 404


def test_a_folder_that_comes_back_is_read(core, liveness, clock, cid, folder):
    shutil.rmtree(folder)
    _files(core, cid)
    shutil.copytree(FIXTURES, folder, ignore=shutil.ignore_patterns("*.md"))
    _rescan(liveness, clock, cid)
    body = _files(core, cid)
    assert body["available"] is True
    assert [row["name"] for row in body["rows"]] == NAMES


def test_a_folder_that_vanishes_keeps_its_rows(core, liveness, clock, cid, folder):
    before = _files(core, cid)
    shutil.rmtree(folder)
    _rescan(liveness, clock, cid)
    body = _files(core, cid)
    assert body["available"] is False
    assert [row["name"] for row in body["rows"]] == NAMES
    status, state = _call(core, "GET", f"/api/{cid}/state")
    assert (status, state["available"]) == (200, False)
    assert body["generation"] == before["generation"]


# --------------------------------------------------------------------------- #
# Rescans
# --------------------------------------------------------------------------- #
def test_a_rescan_sees_a_removed_file(core, liveness, clock, cid, folder):
    before = _files(core, cid)["generation"]
    (folder / "0.0.96.tla").unlink()
    _rescan(liveness, clock, cid)
    body = _files(core, cid)
    assert body["generation"] > before
    assert _row(body, "0.0.96.tla")["state"] == "unavailable"
    _, state = _call(core, "GET", f"/api/{cid}/state")
    assert (state["generation"], state["unavailable"]) == (body["generation"], 1)
    assert state["last_scan"]


def test_a_rescan_sees_an_added_file(core, liveness, clock, cid, folder):
    _files(core, cid)
    shutil.copy(folder / "0.7.0.tla", folder / "copy.tla")
    _rescan(liveness, clock, cid)
    names = [row["name"] for row in _files(core, cid)["rows"]]
    assert "copy.tla" in names


def test_a_rescan_without_changes_keeps_the_generation(core, liveness, clock, cid):
    before = _files(core, cid)["generation"]
    _rescan(liveness, clock, cid)
    assert _files(core, cid)["generation"] == before


def test_queries_see_the_rescanned_index(core, liveness, clock, cid, folder):
    body = {"query": "Exposição THEN Development", "limit": None, "tab": "t"}
    assert _call(core, "POST", f"/api/{cid}/ql", body)[1]["total"] == 3
    (folder / "0.0.96.tla").unlink()
    _rescan(liveness, clock, cid)
    assert _call(core, "POST", f"/api/{cid}/ql", body)[1]["total"] == 2


# --------------------------------------------------------------------------- #
# The backend's scan reports
# --------------------------------------------------------------------------- #
def test_scan_reports_what_changed(folder):
    backend = CoreBackend()
    handle = backend.open_corpus(folder)
    assert backend.scan(handle) == {
        "changed": [],
        "added": [],
        "removed": [],
        "unreadable": [],
        "unavailable": [],
    }
    (folder / "0.0.96.tla").rename(folder / "moved.tla")
    (folder / "broken.tla").write_text("{\n\n  nope", encoding="utf-8")
    (folder / "0.5.15.tla").unlink()
    report = backend.scan(handle)
    assert report["unavailable"] == ["0.5.15.tla"]
    assert report["removed"] == ["0.0.96.tla"]
    assert report["changed"] == ["moved.tla"]
    [broken] = report["unreadable"]
    assert (broken["path"], broken["line"]) == ("broken.tla", 3)
    assert broken["message"]


def test_reread_reads_one_file(folder):
    backend = CoreBackend()
    handle = backend.open_corpus(folder)
    shutil.copy(folder / "0.7.0.tla", folder / "saved.tla")
    assert backend.reread(handle, folder / "saved.tla")["added"] == ["saved.tla"]
    outside = folder.parent / "elsewhere.tla"
    assert backend.reread(handle, outside) == backend.scan(handle)


def test_a_saved_window_rereads_its_file(core, cid, folder):
    _files(core, cid)
    status, window = _call(core, "POST", "/api/windows", {"pid": 1, "files": []})
    assert status == 200
    shutil.copy(folder / "0.7.0.tla", folder / "saved.tla")
    saved = f"/api/windows/{window['window']}/saved"
    assert _call(core, "POST", saved, {"path": str(folder / "saved.tla")})[0] == 204
    assert "saved.tla" in [row["name"] for row in _files(core, cid)["rows"]]
