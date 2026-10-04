from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import send
from support.fixture_backend import FixtureBackend

from tilia_library.api import register_all
from tilia_library.backend import CoreBackend, NotAvailable
from tilia_library.corpora import Corpora, CorpusHandles
from tilia_library.server import LibraryServer


class CountingBackend(FixtureBackend):
    def __init__(self) -> None:
        super().__init__()
        self.opened: list[Path] = []
        self.fail = False

    def open_corpus(self, path):
        if self.fail:
            raise NotAvailable("the index")
        self.opened.append(path)
        return super().open_corpus(path)


def _get(server, path):
    reply = send(server, "GET", path, {"Authorization": f"Bearer {server.token}"})
    return reply.status, json.loads(reply.body)


@pytest.fixture
def corpus_dir(tmp_path):
    folder = tmp_path / "pieces"
    folder.mkdir()
    return folder


@pytest.fixture
def corpora(tmp_path, corpus_dir):
    listed = Corpora(tmp_path / "library.toml")
    listed.add(corpus_dir)
    return listed


@pytest.fixture
def cid(corpora):
    return corpora.all()[0].id


@pytest.fixture
def library(corpora):
    server = LibraryServer(FixtureBackend())
    register_all(server, corpora)
    server.start()
    yield server
    server.stop()


def test_files_listing(library, cid):
    status, data = _get(library, f"/api/{cid}/files")
    assert status == 200
    assert isinstance(data["generation"], int)
    assert data["available"] is True
    assert data["rows"]
    for row in data["rows"]:
        assert {"file_id", "name", "path", "state", "reason", "fields"} <= set(row)
        assert row["state"] in ("ok", "unreadable", "unavailable")
        assert {"count", "kinds"} == set(row["timelines"])


def test_file_detail(library, cid):
    _, listing = _get(library, f"/api/{cid}/files")
    file_id = listing["rows"][0]["file_id"]
    status, data = _get(library, f"/api/{cid}/files/{file_id}")
    assert status == 200
    assert data["file_id"] == file_id
    assert {"name", "path", "fields", "generation"} <= set(data)
    assert data["timelines"]
    for timeline in data["timelines"]:
        assert {"id", "name", "kind", "fields"} <= set(timeline)


def test_unknown_corpus_and_file(library, cid):
    assert _get(library, "/api/nope-0000/files") == (404, {"error": "unknown corpus"})
    assert _get(library, "/api/nope-0000/files/f1") == (
        404,
        {"error": "unknown corpus"},
    )
    assert _get(library, f"/api/{cid}/files/nope") == (404, {"error": "unknown file"})


def test_core_backend_is_not_available(corpora, cid):
    server = LibraryServer(CoreBackend())
    register_all(server, corpora)
    server.start()
    try:
        assert _get(server, f"/api/{cid}/files") == (
            501,
            {"error": "not available yet", "needs": "the index"},
        )
    finally:
        server.stop()


def test_missing_folder_is_unavailable(library, corpora, cid, corpus_dir):
    corpus_dir.rmdir()
    _, listing = _get(library, "/api/library")
    assert [c["available"] for c in listing["corpora"]] == [False]
    status, data = _get(library, f"/api/{cid}/files")
    assert status == 200
    assert data["available"] is False


def test_getting_files_does_not_mark_the_corpus_opened(library, corpora, cid):
    before = corpora.get(cid).last_opened
    _get(library, f"/api/{cid}/files")
    assert corpora.get(cid).last_opened == before


def test_handles_open_each_corpus_once(tmp_path, corpora, cid, corpus_dir):
    backend = CountingBackend()
    handles = CorpusHandles(backend, corpora)
    other = tmp_path / "other"
    other.mkdir()
    other_id = corpora.add(other).id
    corpus, handle = handles.get(cid)
    assert corpus.id == cid
    assert handles.get(cid)[1] is handle
    handles.get(other_id)
    handles.get(other_id)
    assert backend.opened == [corpus_dir.resolve(), other.resolve()]
    with pytest.raises(KeyError):
        handles.get("nope-0000")


def test_handles_do_not_cache_not_available(corpora, cid):
    backend = CountingBackend()
    backend.fail = True
    handles = CorpusHandles(backend, corpora)
    with pytest.raises(NotAvailable):
        handles.get(cid)
    backend.fail = False
    handles.get(cid)
    handles.get(cid)
    assert len(backend.opened) == 1
