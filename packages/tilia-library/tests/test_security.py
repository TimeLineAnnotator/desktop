from __future__ import annotations

import json
import re

import pytest
from conftest import send

from tilia_library.security import cookie_name, new_token
from tilia_library.server import LibraryServer, json_response

SAMPLES = {"cid": "c1", "file": "f1", "x": "1", "path": "index.html"}


@pytest.fixture
def srv():
    from support.fixture_backend import FixtureBackend

    server = LibraryServer(FixtureBackend())
    ok = lambda request: json_response({"ok": True})  # noqa: E731
    server.router.add("POST", "/api/probe", ok)
    server.router.add("DELETE", "/api/probe/{x}", ok)
    server.router.add("POST", "/api/bearer-probe", ok, access="bearer")
    server.start()
    yield server
    server.stop()


def concrete(pattern):
    return re.sub(
        r"\{(\w+)(?::path)?\}", lambda m: SAMPLES.get(m.group(1), "v"), pattern
    )


def bearer(srv):
    return {"Authorization": f"Bearer {srv.token}"}


def cookie(srv, token=None):
    return {"Cookie": f"{cookie_name(srv.port)}={token or srv.token}"}


JSON = {"Content-Type": "application/json"}


def body_for(route):
    return b"{}" if route.method not in ("GET", "HEAD") else None


def all_routes(srv):
    return [(r, concrete(r.pattern)) for r in srv.router.routes]


def test_access_matrix(srv):
    port = srv.port
    replies = []

    def go(route, path, headers, host="default"):
        r = send(srv, route.method, path, headers, body_for(route), host=host)
        replies.append(r)
        return r

    assert len(srv.router.routes) >= 6
    for route, path in all_routes(srv):
        base = dict(JSON) if route.method not in ("GET", "HEAD") else {}
        # a. credentials
        assert go(route, path, base).status == 403
        assert go(route, path, {**base, "Authorization": "Bearer nope"}).status == 403
        assert go(route, path, {**base, **cookie(srv, "nope")}).status == 403
        # b. host
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
        c = {**cookie(srv), **JSON}
        if route.access == "any":
            assert go(route, path, c).status == 403
            ok = {**c, "X-Tilia-Library": "1"}
            assert go(route, path, ok).status == 200
            for origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
                assert go(route, path, {**ok, "Origin": origin}).status == 200
            assert (
                go(route, path, {**good, "Origin": f"http://127.0.0.1:{port}"}).status
                == 200
            )
        else:
            # e. bearer only
            assert go(route, path, {**c, "X-Tilia-Library": "1"}).status == 403
            assert go(route, path, good).status == 200
    # f. no CORS grants
    for r in replies:
        assert not [h for h in r.headers if h.startswith("access-control-allow-")]


def test_entry_sets_cookie(srv):
    r = send(srv, "GET", f"/?token={srv.token}")
    assert r.status == 303
    assert r.headers["location"] == "/"
    (cookie_line,) = r.set_cookies
    name, _, rest = cookie_line.partition("=")
    assert name == f"tilia-library-{srv.port}"
    assert rest.split(";")[0] == srv.token
    attrs = [a.strip().lower() for a in rest.split(";")[1:]]
    assert "httponly" in attrs
    assert "samesite=lax" in attrs
    assert "path=/" in attrs
    assert not [a for a in attrs if a.startswith(("max-age", "expires"))]
    r2 = send(srv, "GET", "/", {"Cookie": f"{name}={srv.token}"})
    assert r2.status == 200
    assert r2.headers["content-type"].startswith("text/html")


def test_entry_wrong_token(srv):
    r = send(srv, "GET", "/?token=wrong")
    assert r.status == 403
    assert r.set_cookies == []


def test_entry_checks_host_first(srv):
    r = send(srv, "GET", f"/?token={srv.token}", host="evil.example")
    assert r.status == 400


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


def test_malformed_cookie_is_no_cookie(srv):
    r = send(srv, "GET", "/api/ping", {"Cookie": "\x01garbage;;=="})
    assert r.status == 403


def ping_with_cookie(srv, value):
    return send(srv, "GET", "/api/ping", {"Cookie": value}).status


def test_cookie_found_among_unparseable_cookies(srv):
    ours = f"{cookie_name(srv.port)}={srv.token}"
    header = (
        f'prefs={{"a":1,"b":"x y"}}; theme=[dark]; q="unterminated; {ours}; after=1'
    )
    assert ping_with_cookie(srv, header) == 200


def test_cookie_in_second_cookie_header(srv):
    import http.client

    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    conn.putrequest("GET", "/api/ping", skip_host=True)
    conn.putheader("Host", f"127.0.0.1:{srv.port}")
    conn.putheader("Cookie", "other=1")
    conn.putheader("Cookie", f"{cookie_name(srv.port)}={srv.token}")
    conn.endheaders()
    assert conn.getresponse().status == 200
    conn.close()


def test_cookie_name_must_match_exactly(srv):
    name = cookie_name(srv.port)
    assert ping_with_cookie(srv, f"x{name}={srv.token}") == 403
    assert ping_with_cookie(srv, f"{name}x={srv.token}") == 403


def test_cookie_with_wrong_value_is_refused(srv):
    assert ping_with_cookie(srv, f"{cookie_name(srv.port)}={srv.token}x") == 403


def test_token_under_another_port_name_is_refused(srv):
    assert ping_with_cookie(srv, f"{cookie_name(srv.port + 1)}={srv.token}") == 403


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


@pytest.mark.parametrize(
    "path",
    [
        "/web/../server.py",
        "/web/%2e%2e/server.py",
        "/web/..%2fserver.py",
        "/web/%5c..%5cserver.py",
        "/web//etc/passwd",
        "/web/C:/Windows/win.ini",
        "/web/",
        "/web/sub/",
    ],
)
def test_no_traversal(srv, path):
    from pathlib import Path

    import tilia_library.server as module

    r = send(srv, "GET", path, bearer(srv))
    assert r.status == 404
    assert r.body != Path(module.__file__).read_bytes()


def test_403_page_for_non_api_is_html(srv):
    r = send(srv, "GET", "/")
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
