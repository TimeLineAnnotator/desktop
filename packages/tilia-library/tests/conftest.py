from __future__ import annotations

import http.client
from dataclasses import dataclass, field

import pytest
from support.fixture_backend import FixtureBackend

from tilia_library.server import LibraryServer


@dataclass
class Reply:
    status: int
    headers: dict[str, str]
    body: bytes
    set_cookies: list[str] = field(default_factory=list)


def send(
    server,
    method,
    path,
    headers=None,
    body=None,
    host="default",
    conn=None,
):
    """Send one request with exactly the given headers; host=None sends none."""
    own = conn is None
    if own:
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    try:
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        if host == "default":
            host = f"127.0.0.1:{server.port}"
        if host is not None:
            conn.putheader("Host", host)
        for name, value in (headers or {}).items():
            conn.putheader(name, value)
        if body is not None:
            conn.putheader("Content-Length", str(len(body)))
        conn.endheaders(body)
        resp = conn.getresponse()
        data = resp.read()
        return Reply(
            resp.status,
            {k.lower(): v for k, v in resp.getheaders()},
            data,
            resp.msg.get_all("Set-Cookie") or [],
        )
    finally:
        if own:
            conn.close()


@pytest.fixture
def send_to():
    return send


@pytest.fixture
def server():
    srv = LibraryServer(FixtureBackend())
    srv.start()
    yield srv
    srv.stop()
