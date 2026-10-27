from __future__ import annotations

import http.client
import json
import logging
import os
import sys
import time

import pytest
from conftest import send
from support.fixture_backend import FixtureBackend

from tilia_library.server import PROTOCOL, LibraryServer

TYPES = {
    "a.html": "text/html; charset=utf-8",
    "a.js": "text/javascript; charset=utf-8",
    "a.mjs": "text/javascript; charset=utf-8",
    "a.css": "text/css; charset=utf-8",
    "a.svg": "image/svg+xml",
    "a.png": "image/png",
    "a.woff2": "font/woff2",
    "a.json": "application/json; charset=utf-8",
}


@pytest.fixture
def web_srv(tmp_path):
    root = tmp_path / "web"
    root.mkdir()
    for name in [*TYPES, "a.txt", "a.py"]:
        (root / name).write_bytes(b"content of " + name.encode())
    (root / "index.html").write_text("<!doctype html><h1>hi</h1>")
    (root / "sub").mkdir()
    server = LibraryServer(FixtureBackend(), web_root=root)
    server.start()
    yield server
    server.stop()


def auth(srv):
    return {"Authorization": f"Bearer {srv.token}"}


@pytest.mark.parametrize("name,ctype", TYPES.items())
def test_content_types(web_srv, name, ctype):
    r = send(web_srv, "GET", f"/web/{name}", auth(web_srv))
    assert r.status == 200
    assert r.headers["content-type"] == ctype
    assert r.body == b"content of " + name.encode()


@pytest.mark.parametrize("name", ["a.txt", "a.py", "missing.js", "sub"])
def test_other_files_are_404(web_srv, name):
    assert send(web_srv, "GET", f"/web/{name}", auth(web_srv)).status == 404


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need privileges")
def test_symlink_out_of_root_is_404(web_srv, tmp_path):
    outside = tmp_path / "secret.html"
    outside.write_text("secret")
    os.symlink(outside, web_srv.web_root / "link.html")
    assert send(web_srv, "GET", "/web/link.html", auth(web_srv)).status == 404


def test_index(web_srv):
    r = send(web_srv, "GET", "/", auth(web_srv))
    assert r.status == 200
    assert b"<h1>hi</h1>" in r.body


def test_default_web_root_has_index(server):
    r = send(server, "GET", "/", auth(server))
    assert r.status == 200
    assert b"TiLiA Library" in r.body


def test_head(web_srv):
    r = send(web_srv, "HEAD", "/web/a.js", auth(web_srv))
    assert r.status == 200
    assert r.body == b""
    assert r.headers["content-length"] == str(len(b"content of a.js"))
    assert r.headers["content-type"] == TYPES["a.js"]


def test_ping(server):
    r = send(server, "GET", "/api/ping", auth(server))
    data = json.loads(r.body)
    assert data["instance"] == server.instance
    assert data["library_version"] == server.library_version
    assert data["protocol"] == PROTOCOL == 1


def test_unknown_path_404(server):
    r = send(server, "GET", "/api/nothing", auth(server))
    assert r.status == 404
    assert "error" in json.loads(r.body)


def test_wrong_method_405(server):
    r = send(
        server,
        "POST",
        "/api/ping",
        {**auth(server), "Content-Type": "application/json"},
        b"{}",
    )
    assert r.status == 405
    allow = {m.strip() for m in r.headers["allow"].split(",")}
    assert allow == {"GET", "HEAD"}


def test_huge_body_413(server):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    conn.putrequest("POST", "/api/ping", skip_host=True)
    conn.putheader("Host", f"127.0.0.1:{server.port}")
    conn.putheader("Content-Length", str(17 * 1024 * 1024))
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Authorization", f"Bearer {server.token}")
    conn.endheaders()
    r = conn.getresponse()
    assert r.status == 413
    assert r.getheader("Connection") == "close"
    conn.close()


def test_chunked_400(server):
    r = send(
        server,
        "POST",
        "/api/ping",
        {**auth(server), "Transfer-Encoding": "chunked"},
    )
    assert r.status == 400
    assert r.headers["connection"] == "close"


def test_keep_alive(server):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    for _ in range(2):
        assert send(server, "GET", "/api/ping", auth(server), conn=conn).status == 200
    conn.close()


def test_keep_alive_after_403_with_body(server):
    conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    body = b'{"a": "' + b"x" * 5000 + b'"}'
    r = send(
        server,
        "POST",
        "/api/ping",
        {"Content-Type": "application/json"},
        body,
        conn=conn,
    )
    assert r.status == 403
    assert send(server, "GET", "/api/ping", auth(server), conn=conn).status == 200
    conn.close()


def test_security_headers_everywhere(server):
    for path, headers in [
        ("/api/ping", auth(server)),
        ("/api/ping", {}),
        ("/api/none", auth(server)),
        ("/", {}),
        (f"/?token={server.token}", {}),
    ]:
        r = send(server, "GET", path, headers)
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["referrer-policy"] == "no-referrer"
        assert r.headers["cache-control"] == "no-store"
        assert "content-length" in r.headers


def test_content_security_policy_everywhere(web_srv):
    from tilia_library.server import CONTENT_SECURITY_POLICY

    for path in ("/", "/web/a.js", "/api/ping", "/api/none"):
        r = send(web_srv, "GET", path, auth(web_srv))
        assert r.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    r = send(web_srv, "GET", "/", {})
    assert r.status == 403
    assert "content-security-policy" in r.headers


def test_content_security_policy_text(server):
    policy = send(server, "GET", "/api/ping", auth(server)).headers[
        "content-security-policy"
    ]
    directives = {d.split(" ", 1)[0]: d.split(" ", 1)[1] for d in policy.split("; ")}
    assert directives == {
        "default-src": "'self'",
        "script-src": "'self'",
        "style-src": "'self' 'unsafe-inline'",
        "img-src": "'self' data: blob:",
        "media-src": "'self'",
        "connect-src": "'self'",
        "frame-src": "https://www.youtube-nocookie.com",
        "object-src": "'none'",
        "base-uri": "'none'",
        "form-action": "'none'",
        "frame-ancestors": "'none'",
    }


def test_bound_port_raises():
    first = LibraryServer(FixtureBackend())
    try:
        with pytest.raises(OSError):
            LibraryServer(FixtureBackend(), port=first.port)
    finally:
        first.stop()


def test_given_token_and_urls():
    with LibraryServer(FixtureBackend(), token="abc", instance="i1") as srv:
        assert srv.token == "abc"
        assert srv.instance == "i1"
        assert srv.address == f"http://127.0.0.1:{srv.port}/"
        assert srv.entry_url == f"http://127.0.0.1:{srv.port}/?token=abc"


def test_token_not_logged(server, caplog):
    with caplog.at_level(logging.DEBUG):
        send(server, "GET", f"/?token={server.token}")
        send(server, "GET", f"/?token={server.token}", auth(server))
    assert caplog.records
    for record in caplog.records:
        assert server.token not in record.getMessage()
        assert server.token not in str(record.__dict__)
    assert any("token=…" in r.getMessage() for r in caplog.records)


def test_stop_is_idempotent_and_quick():
    started = time.monotonic()
    srv = LibraryServer(FixtureBackend())
    srv.stop()
    srv.stop()
    srv = LibraryServer(FixtureBackend())
    srv.start()
    srv.stop()
    srv.stop()
    assert time.monotonic() - started < 5


def test_serve_forever_in_calling_thread():
    import threading

    srv = LibraryServer(FixtureBackend())
    thread = threading.Thread(target=srv.serve_forever)
    thread.start()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        try:
            if (
                send(
                    srv, "GET", "/api/ping", {"Authorization": f"Bearer {srv.token}"}
                ).status
                == 200
            ):
                break
        except OSError:
            time.sleep(0.05)
    srv.stop()
    thread.join(5)
    assert not thread.is_alive()
