from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from conftest import send
from support.fixture_backend import FixtureBackend

from tilia_core.library_link import (
    ChangedByEdit,
    LibraryLink,
    OpenFile,
    ServerRecord,
    WindowForgotten,
)
from tilia_library.api import register_all
from tilia_library.corpora import Corpora
from tilia_library.liveness import Liveness
from tilia_library.previews import Previews
from tilia_library.server import LibraryServer
from tilia_library.windows import Windows, path_key

K1 = "f1:u1-u2"  # a set on label, in f1


class RecordingBackend(FixtureBackend):
    """Records the skip_files and paths it is given; its undo can be held."""

    def __init__(self):
        super().__init__()
        self.skipped = {"plan": [], "apply": [], "undo": []}
        self.rereads = []
        self.undos = 0
        self.undone = set()
        self.hold = None  # an Event the undo waits on
        self.inside = threading.Event()

    def plan(self, corpus, statement, skip_files):
        self.skipped["plan"].append(set(skip_files))
        return super().plan(corpus, statement, skip_files)

    def apply(self, corpus, plan, keys, skip_files):
        self.skipped["apply"].append(set(skip_files))
        return super().apply(corpus, plan, keys, skip_files)

    def undo(self, corpus, entry, skip_files):
        self.skipped["undo"].append(set(skip_files))
        self.undos += 1
        self.inside.set()
        if self.hold is not None:
            assert self.hold.wait(5)
        result = super().undo(corpus, entry, skip_files)
        self.undone.add(entry)
        return result

    def edit_log(self, corpus):
        log = super().edit_log(corpus)
        for entry in log:
            if entry["entry"] in self.undone:
                entry["undone"] = True
        return log

    def reread(self, corpus, path):
        self.rereads.append((corpus, path))
        return super().reread(corpus, path)


class SpyLiveness(Liveness):
    def __init__(self, backend):
        super().__init__(backend)
        self.poked = []

    def poke(self, cid):
        self.poked.append(cid)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


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
def folder(corpora):
    return corpora.all()[0].path


@pytest.fixture
def backend():
    return RecordingBackend()


@pytest.fixture
def liveness(backend):
    return SpyLiveness(backend)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def handles_and_library(backend, corpora, liveness, clock):
    server = LibraryServer(backend)
    handles = register_all(
        server,
        corpora,
        liveness,
        previews=Previews(ttl=100.0, clock=clock),
        windows=Windows(clock=clock),
    )
    server.start()
    yield handles, server
    server.stop()


@pytest.fixture
def handles(handles_and_library):
    return handles_and_library[0]


@pytest.fixture
def library(handles_and_library):
    return handles_and_library[1]


@pytest.fixture
def link(library):
    record = ServerRecord.new(f"http://127.0.0.1:{library.port}/", library.token, "t")
    return LibraryLink(record, 1, "test")


def _call(server, method, path, body=None, token=True):
    headers = {"Authorization": f"Bearer {server.token}"} if token else {}
    data = None
    if method != "GET":
        headers["Content-Type"] = "application/json"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    reply = send(server, method, path, headers, data)
    return reply.status, (json.loads(reply.body) if reply.body else None)


def _apply(library, cid):
    _, preview = _call(
        library,
        "POST",
        f"/api/{cid}/ql-edit",
        {"statement": "a -> SET label = 'x'", "tab": "t"},
    )
    return _call(
        library,
        "POST",
        f"/api/{cid}/ql-apply",
        {"preview": preview["preview"], "only": [K1]},
    )


def _undo(library, cid, entry="e3"):
    return _call(library, "POST", f"/api/{cid}/edit-log/{entry}/undo", {})


def f1(folder):
    return folder / "corpus" / "Überleitung.tla"


# 1
def test_register_answers_the_lease_and_a_first_sync_has_no_events(link, folder):
    lease = link.register(7, [OpenFile(str(f1(folder)), False)])
    assert (lease.poll_seconds, lease.lease_seconds) == (2, 15)
    assert lease.window
    assert link.sync(lease.window, [OpenFile(str(f1(folder)), False)]) == []


# 2
def test_an_unsaved_file_is_skipped_until_saved(link, library, backend, cid, folder):
    path = f1(folder).resolve()
    window = link.register(7, [OpenFile(str(path), True)]).window
    _, preview = _call(
        library,
        "POST",
        f"/api/{cid}/ql-edit",
        {"statement": "a -> SET label = 'x'", "tab": "t"},
    )
    _call(
        library,
        "POST",
        f"/api/{cid}/ql-apply",
        {"preview": preview["preview"], "only": [K1]},
    )
    _undo(library, cid)
    assert backend.skipped["plan"][0] == {path}
    assert backend.skipped["apply"] == [{path}]
    assert backend.skipped["undo"] == [{path}]
    link.sync(window, [OpenFile(str(path), False)])
    _undo(library, cid, "e2")
    assert backend.skipped["undo"][-1] == set()


# 3
def test_saved_rereads_the_file_in_its_open_corpus(
    link, library, backend, handles, liveness, cid, folder
):
    window = link.register(7, []).window
    path = f1(folder)
    link.saved(window, str(path))
    assert backend.rereads == []  # the corpus isn't open: asking opens nothing
    _, handle = handles.get(cid)
    link.saved(window, str(path))
    assert backend.rereads == [(handle, path.resolve())]
    assert liveness.poked == [cid]
    link.saved(window, str(folder.parent / "elsewhere" / "x.tla"))
    assert len(backend.rereads) == 1 and liveness.poked == [cid]


# 4
@pytest.mark.parametrize("how", ["apply", "undo"])
def test_a_window_with_the_file_open_hears_of_the_edit_once(
    link, library, cid, folder, how
):
    path = str(f1(folder))
    first = link.register(7, [OpenFile(path, False)]).window
    other = link.register(8, [OpenFile(str(folder / "other.tla"), False)]).window
    if how == "apply":
        status, answer = _apply(library, cid)
        entry = answer["entry"]
    else:
        status, answer = _undo(library, cid)
        entry = "e3"
    assert status == 200
    events = link.sync(first, [OpenFile(path, False)])
    assert [(e.path, e.corpus, e.entry) for e in events] == [(path, cid, entry)]
    assert isinstance(events[0], ChangedByEdit)
    assert link.sync(first, [OpenFile(path, False)]) == []
    assert link.sync(other, [OpenFile(str(folder / "other.tla"), False)]) == []


# 5
def test_a_silent_window_is_forgotten(link, library, backend, clock, cid, folder):
    path = str(f1(folder))
    window = link.register(7, [OpenFile(path, True)]).window
    clock.now = 14.0
    _undo(library, cid)
    assert backend.skipped["undo"][-1] == {Path(path).resolve()}
    clock.now = 14.0 + 15.1
    _undo(library, cid, "e2")
    assert backend.skipped["undo"][-1] == set()
    with pytest.raises(WindowForgotten):
        link.sync(window, [])
    with pytest.raises(WindowForgotten):
        link.saved(window, path)


def test_every_message_renews_the_lease(link, clock, folder):
    window = link.register(7, []).window
    for now in (10.0, 20.0, 30.0):
        clock.now = now
        link.sync(window, [])
    clock.now = 44.0
    link.saved(window, str(folder / "a.tla"))
    clock.now = 58.0
    assert link.sync(window, []) == []


# 6
def test_two_spellings_of_a_path_are_one_file(link, library, cid, folder):
    (folder / "sub").mkdir()
    spelled = f"{folder}/sub/../a.tla"
    plain = f"{folder}/a.tla"
    assert path_key(spelled) == path_key(plain)
    windows = Windows()
    window = windows.register(1, [(spelled, True)])
    assert windows.unsaved() == {Path(plain).resolve()}
    windows.sync(window, [(plain, True)])
    assert windows.unsaved() == {Path(plain).resolve()}
    windows.written([Path(spelled)], "c", "e1")
    events = windows.sync(window, [(plain, True)])
    assert [e["entry"] for e in events] == ["e1"]


# 7
def test_routes_refuse_the_cookie_and_bad_bodies(library, link):
    window = link.register(7, []).window
    for method, path in (
        ("POST", "/api/windows"),
        ("POST", f"/api/windows/{window}/sync"),
        ("POST", f"/api/windows/{window}/saved"),
        ("DELETE", f"/api/windows/{window}"),
    ):
        reply = send(
            library,
            method,
            path,
            {"Cookie": "x=y", "Content-Type": "application/json"},
            b"{}",
        )
        assert reply.status == 403
    absolute = str(Path("/a/b.tla").resolve())
    for body in (
        {},
        {"pid": "7", "files": []},
        {"pid": True, "files": []},
        {"pid": 7, "files": {}},
        {"pid": 7, "files": ["x"]},
        {"pid": 7, "files": [{"path": 3, "unsaved": False}]},
        {"pid": 7, "files": [{"path": "rel.tla", "unsaved": False}]},
        {"pid": 7, "files": [{"path": absolute, "unsaved": "no"}]},
        {"pid": 7, "files": [{"path": absolute}]},
        [],
    ):
        assert _call(library, "POST", "/api/windows", body)[0] == 400
    for body in ({}, {"files": "x"}, {"files": [{"unsaved": True}]}):
        assert _call(library, "POST", f"/api/windows/{window}/sync", body)[0] == 400
    for body in ({}, {"path": 3}, {"path": "relative.tla"}):
        assert _call(library, "POST", f"/api/windows/{window}/saved", body)[0] == 400
    assert _call(library, "DELETE", "/api/windows/nobody")[0] == 204
    assert _call(library, "POST", "/api/windows/nobody/sync", {"files": []}) == (
        404,
        {"error": "unknown window"},
    )


def test_close_forgets_the_window(link, library, backend, cid, folder):
    path = str(f1(folder))
    window = link.register(7, [OpenFile(path, True)]).window
    link.close(window)
    _undo(library, cid)
    assert backend.skipped["undo"] == [set()]
    with pytest.raises(WindowForgotten):
        link.sync(window, [])


# 8
def test_two_undos_of_one_entry_at_once_reach_the_core_once(library, backend, cid):
    backend.hold = threading.Event()
    answers = []

    def undo():
        answers.append(_undo(library, cid)[0])

    first = threading.Thread(target=undo)
    first.start()
    assert backend.inside.wait(5)
    second = threading.Thread(target=undo)
    second.start()
    backend.hold.set()
    first.join(5)
    second.join(5)
    assert sorted(answers) == [200, 409]
    assert backend.undos == 1
