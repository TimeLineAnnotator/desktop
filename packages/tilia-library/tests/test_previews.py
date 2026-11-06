from __future__ import annotations

import copy
import json
import threading
import time

import pytest
from conftest import send
from support.fixture_backend import FixtureBackend

from tilia_library.api import register_all
from tilia_library.backend import CoreBackend
from tilia_library.corpora import Corpora
from tilia_library.liveness import Liveness
from tilia_library.previews import Previews, same_writes, writes_by_key
from tilia_library.server import LibraryServer

K1 = "f1:u1-u2"  # a set on label
K2 = "f1:u2-u3"  # a delete
K4 = "f4:u7-u8"  # a set on label, in another file


class StatefulBackend(FixtureBackend):
    """Plans label edits against a dict the test can change."""

    def __init__(self):
        super().__init__()
        self.labels = {}
        self.targets = {}
        for entry in self._get("plan")["plan"]:
            for write in entry["writes"]:
                if write["op"] == "set":
                    self.labels[write["component_id"]] = write["old"]
                    self.targets[write["component_id"]] = write["new"]
        self.applied = []

    def plan(self, corpus, statement, skip_files):
        answer = super().plan(corpus, statement, skip_files)
        for entry in answer["plan"]:
            writes = []
            for write in entry["writes"]:
                if write["op"] == "set":
                    comp = write["component_id"]
                    write["old"] = self.labels[comp]
                    write["new"] = self.targets[comp]
                    if write["old"] == write["new"]:
                        continue
                writes.append(write)
            entry["writes"] = writes
        return answer

    def apply(self, corpus, plan, keys, skip_files):
        self.applied.append(set(keys))
        for entry in plan["plan"]:
            if entry["key"] in keys:
                for write in entry["writes"]:
                    if write["op"] == "set":
                        self.labels[write["component_id"]] = write["new"]
        return super().apply(corpus, plan, keys, skip_files)


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
    return StatefulBackend()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def liveness(backend):
    return SpyLiveness(backend)


@pytest.fixture
def library(backend, corpora, liveness, clock):
    server = LibraryServer(backend)
    register_all(server, corpora, liveness, previews=Previews(ttl=100.0, clock=clock))
    server.start()
    yield server
    server.stop()


def _edit(library, cid, **body):
    body.setdefault("statement", 'a -> SET label = "x"')
    body.setdefault("tab", "t1")
    return _call(library, "POST", f"/api/{cid}/ql-edit", body)


def _apply(library, cid, preview, only):
    return _call(
        library, "POST", f"/api/{cid}/ql-apply", {"preview": preview, "only": only}
    )


def _writes(answer, key):
    return next(e["writes"] for e in answer["plan"] if e["key"] == key)


# 1
def test_edit_answers_the_preview(library, cid):
    status, answer = _edit(library, cid)
    assert status == 200
    assert answer["statement"] == 'a -> SET label = "x"'
    assert isinstance(answer["preview"], str) and answer["preview"]
    assert {e["key"] for e in answer["plan"]} >= {K1, K2, K4}
    (write,) = _writes(answer, K1)
    assert (write["field"], write["old"], write["new"]) == (
        "label",
        "Überleitung",
        "Transition",
    )
    assert "summary" in answer and "generation" in answer


def test_preview_keeps_its_writes():
    previews = Previews()
    answer = StatefulBackend().plan(None, "s", set())
    kept = previews.add("c", "t", "s", answer)
    assert previews.get(kept.id) is kept
    assert writes_by_key(kept.answer)[K1][0]["old"] == "Überleitung"
    assert writes_by_key(kept.answer)[K1][0]["new"] == "Transition"


# 2
def test_apply_only_the_ticked_keys(library, backend, liveness, cid):
    _, answer = _edit(library, cid)
    status, result = _apply(library, cid, answer["preview"], [K1, K4])
    assert status == 200
    assert backend.applied == [{K1, K4}]
    assert result["written"] == ["f1", "f4"]
    assert result["entry"]
    assert liveness.poked == [cid]
    assert _apply(library, cid, answer["preview"], [K1])[0] == 410
    assert backend.applied == [{K1, K4}]


# 3
def test_changed_old_value_gives_a_new_preview(library, backend, liveness, cid):
    _, answer = _edit(library, cid)
    backend.labels["u1"] = "edited in TiLiA"
    status, fresh = _apply(library, cid, answer["preview"], [K1])
    assert status == 409
    assert fresh["error"] == "the files changed since the preview"
    assert fresh["preview"] != answer["preview"]
    assert fresh["statement"] == answer["statement"]
    assert _writes(fresh, K1)[0]["old"] == "edited in TiLiA"
    assert backend.applied == [] and liveness.poked == []
    # the new preview is the one to apply now
    assert _apply(library, cid, fresh["preview"], [K1])[0] == 200
    assert backend.applied == [{K1}]


def test_changed_new_value_gives_a_new_preview(library, backend, cid):
    _, answer = _edit(library, cid)
    backend.targets["u1"] = "Something else"
    status, fresh = _apply(library, cid, answer["preview"], [K1])
    assert status == 409
    assert _writes(fresh, K1)[0]["new"] == "Something else"
    assert backend.applied == []


def test_change_in_an_unticked_entry_does_not_matter(library, backend, cid):
    _, answer = _edit(library, cid)
    backend.labels["u7"] = "edited in TiLiA"
    status, _ = _apply(library, cid, answer["preview"], [K1])
    assert status == 200
    assert backend.applied == [{K1}]


# 4
def test_expired_preview(library, clock, cid):
    _, answer = _edit(library, cid)
    clock.now = 101.0
    status, body = _apply(library, cid, answer["preview"], [K1])
    assert status == 410
    assert body == {"error": "the preview expired; preview again"}


def test_preview_of_another_corpus(library, corpora, tmp_path, cid):
    other = tmp_path / "other"
    other.mkdir()
    other_cid = corpora.add(other).id
    _, answer = _edit(library, cid)
    assert _apply(library, other_cid, answer["preview"], [K1])[0] == 410


def test_unknown_key(library, backend, cid):
    _, answer = _edit(library, cid)
    status, body = _apply(library, cid, answer["preview"], [K1, "nope"])
    assert status == 400
    assert body["error"] == "unknown key" and body["detail"] == "nope"
    assert backend.applied == []


def test_unknown_preview(library, cid):
    assert _apply(library, cid, "nothing", [K1])[0] == 410


# 5
def test_previewing_again_after_apply_plans_no_writes(library, cid):
    _, answer = _edit(library, cid)
    assert _apply(library, cid, answer["preview"], [K1, K4])[0] == 200
    _, again = _edit(library, cid)
    assert _writes(again, K1) == [] and _writes(again, K4) == []
    assert _writes(again, K2) != []


# 6
def test_new_preview_replaces_the_tabs_old_one(library, cid):
    _, first = _edit(library, cid, tab="t1")
    _, other = _edit(library, cid, tab="t2")
    _, second = _edit(library, cid, tab="t1")
    assert _apply(library, cid, first["preview"], [K1])[0] == 410
    assert _apply(library, cid, other["preview"], [K4])[0] == 200
    assert _apply(library, cid, second["preview"], [K1])[0] == 200


# 7
@pytest.mark.parametrize("statement", ["", "   \n"])
def test_empty_statement(library, cid, statement):
    status, body = _edit(library, cid, statement=statement)
    assert (status, body) == (400, {"error": "empty statement"})


def test_missing_tab(library, cid):
    status, _ = _call(
        library, "POST", f"/api/{cid}/ql-edit", {"statement": "a -> DELETE"}
    )
    assert status == 400


@pytest.mark.parametrize("only", ["k", [1], {"a": 1}, None])
def test_only_must_be_a_list_of_strings(library, cid, only):
    _, answer = _edit(library, cid)
    assert _apply(library, cid, answer["preview"], only)[0] == 400


def test_query_error(library, cid):
    status, body = _edit(library, cid, statement="a -> error")
    assert status == 400
    assert (body["pos"], body["end"]) == (5, 10)


def test_query_error_when_planning_again(library, backend, cid):
    _, answer = _edit(library, cid)
    backend.plan = lambda *a: (_ for _ in ()).throw(
        __import__("tilia_library.backend").backend.QueryError("bad", 1, 2)
    )
    status, body = _apply(library, cid, answer["preview"], [K1])
    assert status == 400 and body["pos"] == 1


def test_unknown_corpus(library):
    assert _edit(library, "nope")[0] == 404
    assert _apply(library, "nope", "x", [])[0] == 404


def test_core_backend_is_not_available(corpora, cid):
    server = LibraryServer(CoreBackend())
    register_all(server, corpora, SpyLiveness(CoreBackend()))
    server.start()
    try:
        assert _edit(server, cid)[0] == 501
        assert _apply(server, cid, "x", [K1])[0] in (501, 410)
    finally:
        server.stop()


def test_skip_files_reaches_plan_and_apply(backend, corpora, cid, liveness, tmp_path):
    seen = []
    original_plan, original_apply = backend.plan, backend.apply
    backend.plan = lambda c, s, skip: (seen.append(skip), original_plan(c, s, skip))[1]
    backend.apply = lambda c, p, k, skip: (
        seen.append(skip),
        original_apply(c, p, k, skip),
    )[1]
    from tilia_library.api import edits

    server = LibraryServer(backend)
    handles = register_all(server, corpora, liveness)
    # a second registration would clash; build a fresh server for the hook
    server = LibraryServer(backend)
    edits.register(
        server,
        corpora,
        handles,
        liveness,
        Previews(),
        skip_files=lambda c: {tmp_path / "x.tla"},
    )
    server.start()
    try:
        _, answer = _edit(server, cid)
        assert _apply(server, cid, answer["preview"], [K1])[0] == 200
    finally:
        server.stop()
    assert seen == [{tmp_path / "x.tla"}] * 3


# the Previews store and same_writes
def test_ttl_and_discard():
    clock = Clock()
    previews = Previews(ttl=10.0, clock=clock)
    kept = previews.add("c", "t", "s", {"plan": []})
    clock.now = 10.0
    assert previews.get(kept.id) is kept
    clock.now = 10.5
    assert previews.get(kept.id) is None
    other = previews.add("c", "u", "s", {"plan": []})
    previews.discard(other.id)
    previews.discard(other.id)
    assert previews.get(other.id) is None
    assert previews.get("unknown") is None


def test_same_writes():
    old = StatefulBackend().plan(None, "s", set())
    new = copy.deepcopy(old)
    assert same_writes(old, new, [K1, K2, K4])
    assert same_writes(old, new, [])
    assert not same_writes(old, new, ["missing"])
    new["plan"][0]["writes"][0]["extra"] = 1
    assert not same_writes(old, new, [K1])
    assert same_writes(old, new, [K2])
    new = copy.deepcopy(old)
    new["plan"][0]["writes"][0]["new"] = "y"
    assert not same_writes(old, new, [K1])
    new = copy.deepcopy(old)
    new["plan"][0]["writes"].append(new["plan"][0]["writes"][0])
    assert not same_writes(old, new, [K1])
    new = copy.deepcopy(old)
    del new["plan"][0]
    assert not same_writes(old, new, [K1])


def test_add_drops_every_expired_preview():
    clock = Clock()
    previews = Previews(ttl=10.0, clock=clock)
    previews.add("c1", "t1", "s", {"plan": []})
    previews.add("c2", "t2", "s", {"plan": []})
    assert len(previews) == 2
    clock.now = 11.0
    kept = previews.add("c3", "t3", "s", {"plan": []})
    assert len(previews) == 1
    assert previews.get(kept.id) is kept
    clock.now = 20.0
    previews.add("c3", "t3", "s", {"plan": []})
    assert len(previews) == 1


class WaitingBackend(StatefulBackend):
    """An apply that waits until the test lets it go."""

    def __init__(self):
        super().__init__()
        self.release = threading.Event()
        self.entered = threading.Event()

    def apply(self, corpus, plan, keys, skip_files):
        self.entered.set()
        assert self.release.wait(5)
        return super().apply(corpus, plan, keys, skip_files)


def test_two_applies_of_one_preview_write_once(corpora, cid, liveness):
    backend = WaitingBackend()
    server = LibraryServer(backend)
    register_all(server, corpora, liveness)
    server.start()
    try:
        _, answer = _edit(server, cid)
        replies = []

        def apply():
            replies.append(_apply(server, cid, answer["preview"], [K1])[0])

        threads = [threading.Thread(target=apply) for _ in range(2)]
        threads[0].start()
        assert backend.entered.wait(5)
        threads[1].start()
        time.sleep(0.3)  # long enough for the second apply to reach the lock
        backend.release.set()
        for thread in threads:
            thread.join(5)
    finally:
        backend.release.set()
        server.stop()
    assert sorted(replies) == [200, 410]
    assert backend.applied == [{K1}]


def test_empty_only_is_nothing_to_apply(library, backend, cid):
    _, answer = _edit(library, cid)
    status, body = _apply(library, cid, answer["preview"], [])
    assert (status, body) == (400, {"error": "nothing to apply"})
    assert backend.applied == []
    assert _apply(library, cid, answer["preview"], [K1])[0] == 200
