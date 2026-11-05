from __future__ import annotations

import json
import re

import pytest
from conftest import send
from support.fixture_backend import FixtureBackend

from tilia_library.api import register_all
from tilia_library.corpora import Corpora
from tilia_library.security import new_token
from tilia_library.server import LibraryServer, Response, json_response

SAMPLES = {"cid": "c1", "file": "f1", "x": "1", "path": "index.html"}

# All a browser may ask for without the header. The page and its code, which a
# browser can only load without headers and which hold no secret and no data.
PUBLIC = {("GET", "/"), ("GET", "/web/{path:path}")}
# What <audio> asks for: the header, or the media key instead.
MEDIA = {("GET", "/api/{cid}/media/{file}/stream")}


@pytest.fixture
def srv():
    server = LibraryServer(FixtureBackend())
    ok = lambda request: json_response({"ok": True})  # noqa: E731
    server.router.add("POST", "/api/probe", ok)
    server.router.add("DELETE", "/api/probe/{x}", ok)
    server.start()
    yield server
    server.stop()


@pytest.fixture
def full(tmp_path):
    """A server with every route the library has."""
    corpora = Corpora(tmp_path / "library.toml")
    (tmp_path / "pieces").mkdir()
    corpora.add(tmp_path / "pieces")
    server = LibraryServer(FixtureBackend())
    register_all(server, corpora)
    server.start()
    yield server
    server.stop()


def concrete(pattern):
    return re.sub(
        r"\{(\w+)(?::path)?\}", lambda m: SAMPLES.get(m.group(1), "v"), pattern
    )


def bearer(srv):
    return {"Authorization": f"Bearer {srv.token}"}


JSON = {"Content-Type": "application/json"}


def body_for(route):
    return b"{}" if route.method not in ("GET", "HEAD") else None


def base_for(route):
    return dict(JSON) if route.method not in ("GET", "HEAD") else {}


def all_routes(srv):
    return [(r, concrete(r.pattern)) for r in srv.router.routes]


def old_cookies(srv):
    """The cookies that used to be a credential, and other ways to spell one."""
    return (
        f"tilia-library-{srv.port}={srv.token}",
        f"token={srv.token}",
        f"Authorization=Bearer {srv.token}",
    )


def test_access_matrix(srv):
    port = srv.port
    replies = []

    def go(route, path, headers, host="default"):
        r = send(srv, route.method, path, headers, body_for(route), host=host)
        replies.append(r)
        return r

    assert len(srv.router.routes) >= 5
    for route, path in all_routes(srv):
        base = base_for(route)
        # a. credentials
        if route.access == "public":
            assert go(route, path, base).status == 200, route
        else:
            assert go(route, path, base).status == 403
            assert (
                go(route, path, {**base, "Authorization": "Bearer nope"}).status == 403
            )
        # b. host, on every route: the public ones too
        good = {**base, **bearer(srv)}
        for host in (
            "evil.example:%d" % port,
            f"127.0.0.1:{port + 1}",
            None,
        ):
            assert go(route, path, good, host=host).status == 400, (route, host)
        # c. good bearer
        r = go(route, path, good)
        assert r.status not in (400, 403), (route, r.status)
        if route.method == "GET":
            assert r.status == 200, route
        if route.method in ("GET", "HEAD"):
            continue
        # d. method checks
        for origin in ("http://evil.example", f"http://127.0.0.1:{port + 1}", "null"):
            assert go(route, path, {**good, "Origin": origin}).status == 403
        for ctype in ("text/plain", "application/x-www-form-urlencoded", None):
            h = {**bearer(srv)}
            if ctype:
                h["Content-Type"] = ctype
            assert go(route, path, h).status == 403, (route, ctype)
        for origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            assert go(route, path, {**good, "Origin": origin}).status == 200
    # e. no CORS grants
    for r in replies:
        assert not [h for h in r.headers if h.startswith("access-control-allow-")]


# The two properties of the decision of 2026-10-26 (C7).
def test_no_secret_in_any_set_cookie(full):
    """The sweep: no route of the library sets a cookie, with or without the header."""
    for route, path in all_routes(full):
        for headers in ({}, bearer(full)):
            r = send(
                full,
                route.method,
                path,
                {**base_for(route), **headers},
                body_for(route),
            )
            assert r.set_cookies == [], route
    for path in (
        "/",
        "/nothing",
        f"/?token={full.token}",
        "/?token=wrong",
        f"/?media_key={full.media_key}",
    ):
        assert send(full, "GET", path).set_cookies == [], path


@pytest.mark.parametrize("name", ["Set-Cookie", "set-cookie", "SET-COOKIE"])
def test_a_handler_cannot_set_a_cookie(srv, name):
    """The guard: a cookie doesn't leave the server, whoever adds it."""

    def sets_one(request):
        return Response(
            200, b"{}", "application/json", {name: f"a={srv.token}", "X-Kept": "1"}
        )

    srv.router.add("GET", "/api/sets-one", sets_one)
    r = send(srv, "GET", "/api/sets-one", bearer(srv))
    assert r.status == 200
    assert r.headers["x-kept"] == "1"
    assert r.set_cookies == []
    assert srv.token.encode() not in r.body
    assert "set-cookie" not in r.headers


def test_every_non_media_route_refuses_a_request_without_the_header(full):
    routes = full.router.routes
    assert {(r.method, r.pattern) for r in routes if r.access == "public"} == PUBLIC
    assert {(r.method, r.pattern) for r in routes if r.access == "media"} == MEDIA
    guarded = [r for r in routes if r.access == "bearer"]
    assert len(guarded) >= 20
    for route in guarded:
        path = concrete(route.pattern)
        base = base_for(route)
        without = [
            (path, {}),
            (path, {"Authorization": "Bearer nope"}),
            (path, {"Authorization": f"Basic {full.token}"}),
            (path, {"Authorization": f"Bearer {full.media_key}"}),
            (path, {"X-Tilia-Library": "1"}),
            (f"{path}?token={full.token}", {}),
            (f"{path}?media_key={full.media_key}", {}),
            *((path, {"Cookie": c}) for c in old_cookies(full)),
            *((path, {"Cookie": c, "X-Tilia-Library": "1"}) for c in old_cookies(full)),
        ]
        for target, headers in without:
            r = send(full, route.method, target, {**base, **headers}, body_for(route))
            assert r.status == 403, (route.method, route.pattern, headers)
        # The same request with the header passes the checks, so what refused
        # the others was the missing header and nothing else.
        r = send(full, route.method, path, {**base, **bearer(full)}, body_for(route))
        assert r.status != 403, (route.method, route.pattern)


def test_a_new_route_needs_the_header_unless_it_says_otherwise(srv):
    ok = lambda request: json_response({"ok": True})  # noqa: E731
    srv.router.add("GET", "/api/new", ok)
    assert srv.router.routes[-1].access == "bearer"
    assert send(srv, "GET", "/api/new").status == 403
    assert send(srv, "GET", "/api/new", bearer(srv)).status == 200


def test_the_media_route_needs_the_header_or_the_key(full):
    (route,) = [r for r in full.router.routes if r.access == "media"]
    path = concrete(route.pattern)
    for target, headers in (
        (path, {}),
        (f"{path}?media_key=nope", {}),
        (f"{path}?media_key={full.token}", {}),
        (f"{path}?token={full.token}", {}),
        (path, {"Authorization": f"Bearer {full.media_key}"}),
        *((path, {"Cookie": c}) for c in old_cookies(full)),
    ):
        assert send(full, "GET", target, headers).status == 403, (target, headers)
    # Past the check; the corpus of the sample path is unknown.
    assert send(full, "GET", path, bearer(full)).status == 404
    assert send(full, "GET", f"{path}?media_key={full.media_key}").status == 404


def test_a_method_without_a_route_needs_the_header(full):
    for path in ("/", "/web/index.html", "/api/c1/media/f1/stream"):
        query = f"{path}?media_key={full.media_key}"
        assert send(full, "POST", query, JSON, b"{}").status == 403, path
        r = send(full, "POST", path, {**JSON, **bearer(full)}, b"{}")
        assert r.status == 405, path


def test_the_entry_address_keeps_the_token_in_its_fragment(srv):
    assert srv.entry_url == f"{srv.address}#token={srv.token}"


@pytest.mark.parametrize("given", ["right", "wrong"])
def test_a_token_in_the_query_opens_nothing(srv, given):
    token = srv.token if given == "right" else "wrong"
    r = send(srv, "GET", f"/?token={token}")
    assert r.status == 200
    assert "location" not in r.headers
    assert r.set_cookies == []
    assert send(srv, "GET", f"/api/ping?token={token}").status == 403


def test_the_page_holds_no_secret(full):
    for path in ("/", f"/?token={full.token}", "/web/js/auth.js", "/web/js/main.js"):
        r = send(full, "GET", path)
        assert r.status == 200, path
        assert full.token.encode() not in r.body, path
        assert full.media_key.encode() not in r.body, path


def test_public_routes_check_the_host_first(srv):
    assert send(srv, "GET", "/", host="evil.example").status == 400
    assert send(srv, "GET", "/web/index.html", host="evil.example").status == 400
    assert send(srv, "GET", f"/?token={srv.token}", host="evil.example").status == 400


def test_localhost_any_case(srv):
    r = send(srv, "GET", "/api/ping", bearer(srv), host=f"LocalHost:{srv.port}")
    assert r.status == 200


def test_duplicate_host_is_400(srv):
    import http.client

    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    conn.putrequest("GET", "/api/ping", skip_host=True)
    conn.putheader("Host", f"127.0.0.1:{srv.port}")
    conn.putheader("Host", f"127.0.0.1:{srv.port}")
    conn.putheader("Authorization", f"Bearer {srv.token}")
    conn.endheaders()
    assert conn.getresponse().status == 400
    conn.close()


def test_preflight_gets_403(srv):
    r = send(
        srv,
        "OPTIONS",
        "/api/probe",
        {
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.status == 403
    assert not [h for h in r.headers if h.startswith("access-control-allow-")]


@pytest.fixture
def web_srv(tmp_path):
    """A server whose web folder has a file of a served type just outside it."""
    (tmp_path / "secret.json").write_text('{"secret": 1}')
    root = tmp_path / "web"
    root.mkdir()
    (root / "index.html").write_text("<!doctype html>")
    (root / "sub").mkdir()
    server = LibraryServer(FixtureBackend(), web_root=root)
    server.start()
    yield server
    server.stop()


@pytest.mark.parametrize(
    "path",
    [
        "/web/../secret.json",
        "/web/%2e%2e/secret.json",
        "/web/..%2fsecret.json",
        "/web/sub/../../secret.json",
        "/web/%5c..%5csecret.json",
        "/web//etc/passwd",
        "/web/C:/Windows/win.ini",
        "/web/",
        "/web/sub/",
    ],
)
def test_no_traversal_and_no_header_needed_to_find_that_out(web_srv, path):
    r = send(web_srv, "GET", path)
    assert r.status == 404, path
    assert b"secret" not in r.body


def test_403_page_for_non_api_is_html(srv):
    r = send(srv, "GET", "/nothing")
    assert r.status == 403
    assert r.headers["content-type"] == "text/html; charset=utf-8"
    assert b"tilia library" in r.body


def test_403_for_api_is_json(srv):
    r = send(srv, "GET", "/api/ping")
    assert r.status == 403
    assert r.headers["content-type"].startswith("application/json")
    assert "error" in json.loads(r.body)


def test_unknown_path_without_credentials_is_403(srv):
    assert send(srv, "GET", "/api/nothing").status == 403


def test_tokens_are_distinct():
    assert new_token() != new_token()
