from __future__ import annotations

import http.client
import json
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from support import command_runner
from support.fixture_backend import FixtureBackend

from tilia_core.library_link import ServerRecord
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


def api(record, method, path, body=None):
    """Call a running library with its record's token; return status and JSON."""
    port = int(record.address.rstrip("/").rsplit(":", 1)[1])
    headers = {"Authorization": f"Bearer {record.token}"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    reply = send(SimpleNamespace(port=port), method, path, headers, data)
    return reply.status, (json.loads(reply.body) if reply.body else None)


@pytest.fixture
def env(tmp_path):
    """A state folder and a browser log, both inside tmp_path."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return SimpleNamespace(
        state=state_dir,
        log=tmp_path / "browser.log",
        record=lambda: ServerRecord.read(state_dir / "server.toml"),
    )


@pytest.fixture
def launch(env):
    """Start commands through the wrapper; whatever is left is killed after."""
    started = []

    def launch(*arguments):
        running = command_runner.start(env.state, env.log, *arguments)
        started.append(running)
        return running

    yield launch
    for running in started:
        running.kill()
