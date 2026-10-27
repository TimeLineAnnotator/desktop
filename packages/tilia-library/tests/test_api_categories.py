from __future__ import annotations

import json

import pytest
from conftest import send
from support.fixture_backend import FixtureBackend

from tilia_library.api import register_all
from tilia_library.backend import CoreBackend
from tilia_library.corpora import Corpora
from tilia_library.liveness import Liveness
from tilia_library.server import LibraryServer


class SpyBackend(FixtureBackend):
    def __init__(self):
        super().__init__()
        self.folds = []
        self.runs = []
        self.plans = []

    def categories(self, corpus, fold):
        self.folds.append(fold)
        return super().categories(corpus, fold)

    def run(self, corpus, text, **kwargs):
        self.runs.append((text, kwargs))
        return super().run(corpus, text, **kwargs)

    def plan(self, corpus, statement, skip_files):
        self.plans.append(statement)
        return super().plan(corpus, statement, skip_files)


class NoGrammarBackend(SpyBackend):
    def categories(self, corpus, fold):
        answer = super().categories(corpus, fold)
        answer["grammar"] = False
        return answer


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


def serve(backend, corpora):
    server = LibraryServer(backend)
    register_all(server, corpora, Liveness(backend))
    server.start()
    return server


@pytest.fixture
def backend():
    return SpyBackend()


@pytest.fixture
def library(backend, corpora):
    server = serve(backend, corpora)
    yield server
    server.stop()


def _components(library, cid, **body):
    body.setdefault("categories", ["bridge"])
    body.setdefault("mode", "any")
    body.setdefault("fold", False)
    body.setdefault("tab", "t1")
    return _call(library, "POST", f"/api/{cid}/categories/components", body)


def _edit(library, cid, **body):
    body.setdefault("categories", ["bridge"])
    body.setdefault("mode", "any")
    body.setdefault("fold", False)
    body.setdefault("tab", "t1")
    body.setdefault("op", "set")
    body.setdefault("field", "label")
    body.setdefault("value", "X")
    return _call(library, "POST", f"/api/{cid}/categories/edit", body)


def test_categories_are_sorted_by_count_then_name(library, cid):
    status, body = _call(library, "GET", f"/api/{cid}/categories?fold=0")
    assert status == 200
    assert body["grammar"] is True and body["generation"] == 1
    rows = body["categories"]
    assert len(rows) >= 10
    assert [(-r["n"], r["category"]) for r in rows] == sorted(
        (-r["n"], r["category"]) for r in rows
    )
    assert rows[0] == {"category": "chorus", "group": "form", "n": 20}
    assert {r["category"] for r in rows} >= {"bridge", "bridge.modern", "verse 2"}


def test_fold_is_passed_on_and_validated(library, backend, cid):
    status, body = _call(library, "GET", f"/api/{cid}/categories?fold=1")
    assert status == 200 and backend.folds == [True]
    names = {r["category"] for r in body["categories"]}
    assert "bridge.modern" not in names
    assert {r["n"] for r in body["categories"] if r["category"] == "bridge"} == {20}
    for bad in ("2", "yes", ""):
        status, _ = _call(library, "GET", f"/api/{cid}/categories?fold={bad}")
        assert status == 400
    status, _ = _call(library, "GET", f"/api/{cid}/categories")
    assert status == 400


def test_components_run_the_selection(library, backend, cid):
    status, body = _components(library, cid, categories=["bridge", "chorus"])
    assert status == 200
    assert body["statement"] == "bridge OR chorus"
    assert body["rows"] and body["columns"] and body["matches"]
    text, kwargs = backend.runs[0]
    assert text == "bridge OR chorus"
    assert kwargs["max_matches"] > 0 and kwargs["time_limit"] > 0
    assert not kwargs["cancel"].is_set()


def test_components_all_with_a_grammar(library, cid):
    status, body = _components(
        library, cid, categories=["bridge", "chorus"], mode="all"
    )
    assert status == 200 and body["statement"] == "bridge/chorus"


def test_a_category_that_is_not_a_word_is_refused(library, backend, cid):
    status, body = _components(library, cid, categories=["verse 2"])
    assert status == 400
    assert body["error"] == (
        "'verse 2' can't be written in the query language yet: "
        "a category in a query is one word"
    )
    assert backend.runs == []


def test_all_without_a_grammar_is_refused(corpora, cid):
    server = serve(NoGrammarBackend(), corpora)
    try:
        status, body = _components(server, cid, categories=["a", "b"], mode="all")
        assert status == 400
        assert body["error"] == (
            '"all" needs a label grammar: without one, a label has one category'
        )
        status, body = _components(server, cid, categories=["a", "b"])
        assert status == 200 and body["statement"] == "a OR b"
    finally:
        server.stop()


def test_a_query_error_is_a_400(library, cid):
    status, body = _components(library, cid, categories=["error"])
    assert status == 400 and body["error"] and "pos" in body


@pytest.mark.parametrize(
    "change",
    [
        {"categories": "bridge"},
        {"categories": [1]},
        {"mode": 3},
        {"fold": "no"},
        {"tab": ""},
        {"tab": None},
    ],
)
def test_bad_bodies_are_400(library, cid, change):
    assert _components(library, cid, **change)[0] == 400
    assert _edit(library, cid, **change)[0] == 400


def test_a_body_that_is_not_an_object_is_400(library, cid):
    status, _ = _call(library, "POST", f"/api/{cid}/categories/components", [])
    assert status == 400


def test_set_answers_a_preview(library, backend, cid):
    status, body = _edit(library, cid, value='say "hi"')
    assert status == 200
    assert body["statement"] == 'bridge -> SET label = "say \\"hi\\""'
    assert backend.plans == [body["statement"]]
    assert body["preview"] and body["plan"] and body["summary"]


def test_replace_answers_a_preview(library, cid):
    status, body = _edit(
        library,
        cid,
        op="replace",
        pattern="a/b",
        replacement="c",
        categories=["a", "b"],
    )
    assert status == 200
    assert body["statement"] == (
        'a OR b WHERE label ~ /^(.*?)a\\/b(.*)$/ -> SET label = "\\1c\\2"'
    )


def test_the_preview_can_be_applied_with_ql_apply(library, cid):
    _, body = _edit(library, cid)
    key = body["plan"][0]["key"]
    status, applied = _call(
        library,
        "POST",
        f"/api/{cid}/ql-apply",
        {"preview": body["preview"], "only": [key]},
    )
    assert status == 200 and applied["written"]


def test_edit_refusals_are_400s(library, cid):
    cases = [
        ({"categories": []}, "select a category"),
        ({"field": "start"}, None),
        ({"field": "color", "value": "red"}, "a colour is #rrggbb"),
        ({"op": "replace", "pattern": ""}, "the pattern is empty"),
        ({"op": "replace", "pattern": "(x)"}, None),
        ({"op": "replace", "pattern": "x", "replacement": "\\"}, None),
        (
            {"op": "replace", "pattern": "x", "replacement": "y", "every": True},
            "replacing every occurrence can't be written in the query language yet",
        ),
    ]
    for change, text in cases:
        change.setdefault("pattern", "x")
        change.setdefault("replacement", "y")
        status, body = _edit(library, cid, **change)
        assert status == 400, change
        assert body["error"] and (text is None or body["error"] == text)


def test_an_unknown_op_or_a_missing_value_is_400(library, cid):
    assert _edit(library, cid, op="delete")[0] == 400
    assert (
        _call(
            library,
            "POST",
            f"/api/{cid}/categories/edit",
            {
                "categories": ["a"],
                "mode": "any",
                "fold": False,
                "tab": "t",
                "op": "set",
            },
        )[0]
        == 400
    )


def test_unknown_corpus_is_404(library):
    assert _call(library, "GET", "/api/nope/categories?fold=0")[0] == 404
    assert _components(library, "nope")[0] == 404
    assert _edit(library, "nope")[0] == 404


def test_core_backend_is_501(corpora, cid):
    server = serve(CoreBackend(), corpora)
    try:
        assert _call(server, "GET", f"/api/{cid}/categories?fold=0")[0] == 501
        assert _components(server, cid)[0] == 501
        assert _edit(server, cid)[0] == 501
    finally:
        server.stop()
