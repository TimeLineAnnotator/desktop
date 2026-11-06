from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import send
from support.fixture_backend import FixtureBackend

from tilia_library.api import register_all
from tilia_library.backend import CoreBackend
from tilia_library.corpora import Corpora
from tilia_library.liveness import Liveness
from tilia_library.server import LibraryServer

NAMES = {"f1": "Überleitung.tla", "f4": "Переход.tla"}


class SpyBackend(FixtureBackend):
    def __init__(self):
        super().__init__()
        self.undone = []

    def undo(self, corpus, entry, skip_files):
        self.undone.append((entry, skip_files))
        return super().undo(corpus, entry, skip_files)


class SpyLiveness(Liveness):
    def __init__(self, backend):
        super().__init__(backend)
        self.poked = []

    def poke(self, cid):
        self.poked.append(cid)


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


@pytest.fixture
def backend():
    return SpyBackend()


@pytest.fixture
def liveness(backend):
    return SpyLiveness(backend)


@pytest.fixture
def library(backend, corpora, liveness):
    server = LibraryServer(backend)
    register_all(
        server,
        corpora,
        liveness,
        skip_files=lambda cid: {Path("/open/Переход.tla")},
    )
    server.start()
    yield server
    server.stop()


def test_the_log_is_listed_in_the_backends_order(library, cid, backend):
    status, body = _call(library, "GET", f"/api/{cid}/edit-log")
    assert status == 200
    assert body["entries"] == backend.edit_log(None)
    assert [e["entry"] for e in body["entries"]] == ["e3", "e2", "e1"]
    assert body["file_names"] == NAMES  # f9 is no file any more
    assert body["generation"] == 1


def test_undo_answers_what_was_restored_refused_and_skipped(library, cid, backend):
    status, body = _call(library, "POST", f"/api/{cid}/edit-log/e3/undo", {})
    assert status == 200
    assert body["restored"] == ["f1"]
    assert body["refused"] == [
        {"file_id": "f4", "what_changed": "edited in TiLiA after this edit: 2 labels"}
    ]
    assert body["skipped"] == []
    assert body["generation"] == 3
    assert body["file_names"] == NAMES


def test_the_backend_gets_the_entry_and_the_skipped_files(library, cid, backend):
    _call(library, "POST", f"/api/{cid}/edit-log/e2/undo", {})
    assert backend.undone == [("e2", {Path("/open/Переход.tla")})]


def test_liveness_is_poked_after_an_undo(library, cid, liveness):
    _call(library, "GET", f"/api/{cid}/edit-log")
    assert liveness.poked == []
    _call(library, "POST", f"/api/{cid}/edit-log/e3/undo", {})
    assert liveness.poked == [cid]


def test_an_undone_entry_is_refused(library, cid, backend, liveness):
    status, body = _call(library, "POST", f"/api/{cid}/edit-log/e1/undo", {})
    assert (status, body) == (409, {"error": "this edit was already undone"})
    assert backend.undone == []
    assert liveness.poked == []


def test_an_unknown_entry_is_404(library, cid, backend):
    status, body = _call(library, "POST", f"/api/{cid}/edit-log/nope/undo", {})
    assert (status, body) == (404, {"error": "unknown edit"})
    assert backend.undone == []


def test_an_unknown_corpus_is_404(library):
    assert _call(library, "GET", "/api/nope/edit-log")[0] == 404
    assert _call(library, "POST", "/api/nope/edit-log/e3/undo", {})[0] == 404


def test_without_the_core_it_is_501(corpora, cid):
    server = LibraryServer(CoreBackend())
    register_all(server, corpora, SpyLiveness(server.backend))
    server.start()
    try:
        assert _call(server, "GET", f"/api/{cid}/edit-log")[0] == 501
        assert _call(server, "POST", f"/api/{cid}/edit-log/e3/undo", {})[0] == 501
    finally:
        server.stop()
