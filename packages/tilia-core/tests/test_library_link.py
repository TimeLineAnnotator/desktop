import contextlib
import http.server
import json
import socket
import sys
import threading
import time
import urllib.request
from datetime import datetime

import pytest
import tomlkit

from tilia_core import library_link, state
from tilia_core.library_link import (
    ChangedByEdit,
    LibraryLink,
    OpenFile,
    ServerRecord,
    WindowForgotten,
    WindowLease,
    find_library,
    ping,
)


@pytest.fixture(autouse=True)
def redirected(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "state_dir", lambda: tmp_path)
    return tmp_path


def make_record(address="http://127.0.0.1:1/", token="tok"):
    return ServerRecord.new(address, token, "1.2.3")


def test_round_trip(tmp_path):
    record = make_record()
    record.write()
    path = tmp_path / "server.toml"
    assert ServerRecord.default_path() == path
    assert set(tomlkit.parse(path.read_text())) == {
        "version",
        "protocol",
        "library_version",
        "instance",
        "pid",
        "address",
        "token",
        "started",
    }
    back = ServerRecord.read()
    assert back == record
    assert type(back.started) is datetime
    assert back.started.tzinfo is not None and back.started.microsecond == 0
    assert type(back.pid) is int and type(back.token) is str
    assert back.version == 1 and back.protocol == 1


def test_write_to_explicit_path_creates_folders(tmp_path):
    path = tmp_path / "a" / "b" / "s.toml"
    record = make_record()
    record.write(path)
    assert ServerRecord.read(path) == record


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions")
def test_record_mode_is_0600(tmp_path):
    make_record().write()
    assert (tmp_path / "server.toml").stat().st_mode & 0o777 == 0o600


def test_read_is_none_for_bad_files(tmp_path):
    path = tmp_path / "server.toml"
    assert ServerRecord.read() is None
    path.write_text("[[[ nope")
    assert ServerRecord.read() is None
    path.write_bytes(b"\xff\xfe")
    assert ServerRecord.read() is None
    make_record().write()
    doc = tomlkit.parse(path.read_text())
    del doc["token"]
    path.write_text(tomlkit.dumps(doc))
    assert ServerRecord.read() is None
    doc["token"] = 5
    path.write_text(tomlkit.dumps(doc))
    assert ServerRecord.read() is None


def test_read_accepts_newer_version(tmp_path):
    path = tmp_path / "server.toml"
    make_record().write()
    doc = tomlkit.parse(path.read_text())
    doc["version"] = 7
    doc["extra"] = "x"
    path.write_text(tomlkit.dumps(doc))
    assert ServerRecord.read().version == 7


def test_remove_only_for_matching_instance(tmp_path):
    path = tmp_path / "server.toml"
    mine, other = make_record(), make_record()
    other.write()
    assert mine.remove() is False
    assert path.exists()
    mine.write()
    assert mine.remove() is True
    assert not path.exists()
    assert mine.remove() is False


def test_find_library_none_without_record():
    assert find_library() is None


def test_silent_server_times_out():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        s.listen(5)
        make_record(f"http://127.0.0.1:{s.getsockname()[1]}/").write()
        start = time.monotonic()
        assert find_library(timeout=0.3) is None
        assert time.monotonic() - start < 2


@contextlib.contextmanager
def live_server(token, answer):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.headers.get("Authorization") != f"Bearer {token}":
                self.send_response(403)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if self.path != "/api/ping":
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = json.dumps(answer).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def answer_for(record, **changes):
    answer = {
        "instance": record.instance,
        "library_version": "9.9.9",
        "protocol": 1,
    }
    answer.update(changes)
    return answer


def test_find_library_with_live_server():
    box = {}
    with live_server("secret", box) as address:
        record = ServerRecord.new(address, "secret", "1.2.3")
        record.write()
        box.update(answer_for(record))
        link = find_library()
        assert link == LibraryLink(record, 1, "9.9.9")
        box.clear()
        box.update(answer_for(record, instance="someone-else"))
        assert find_library() is None
        box.clear()
        box.update(answer_for(record, protocol=2))
        assert find_library() is None
        box.clear()
        box.update(answer_for(record))
        assert ping(record)["instance"] == record.instance
        wrong = ServerRecord.new(address, "wrong", "1.2.3")
        wrong.write()
        assert ping(wrong) is None


def test_link_request_returns_status_and_json():
    box = {}
    with live_server("t", box) as address:
        record = ServerRecord.new(address, "t", "1")
        box.update(answer_for(record))
        link = LibraryLink(record, 1, "9.9.9")
        for path in ("/api/ping", "api/ping"):
            status, body = link.request("GET", path)
            assert status == 200 and body["instance"] == record.instance
        assert link.request("GET", "/nothing") == (404, None)


def test_ping_ignores_non_loopback_without_connecting(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("must not connect")

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(urllib.request, "build_opener", fail)
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    assert ping(make_record("http://example.com:8765/")) is None
    assert ping(make_record("https://127.0.0.1:8765/")) is None
    assert ping(make_record("http://127.0.0.1/")) is None
    assert library_link.PROTOCOL == 1


@contextlib.contextmanager
def garbage_server():
    """Serve one non-HTTP reply per connection until the block ends."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(0.05)
    stop = threading.Event()

    def serve():
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except OSError:
                continue
            with conn:
                conn.settimeout(2)
                with contextlib.suppress(OSError):
                    conn.recv(65536)
                    conn.sendall(b"garbage\r\n\r\n")

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{listener.getsockname()[1]}/"
    finally:
        stop.set()
        thread.join()
        listener.close()


def test_a_reply_that_is_not_http_raises_os_error_and_ping_is_none():
    with garbage_server() as address:
        record = ServerRecord.new(address, "x", "1")
        with pytest.raises(OSError):
            LibraryLink(record, 1, "x").request("GET", "/api/ping")
    with garbage_server() as address:
        assert ping(ServerRecord.new(address, "x", "1")) is None


@contextlib.contextmanager
def recording_server(token, replies):
    """A stand-in library: records each request, answers from ``replies``.

    ``replies`` maps (method, path) to (status, json answer or None).
    """
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _answer(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            seen.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "body": json.loads(raw) if raw else None,
                    "auth": self.headers.get("Authorization"),
                }
            )
            status, answer = replies.get((self.command, self.path), (404, None))
            body = b"" if answer is None else json.dumps(answer).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_POST = do_DELETE = _answer

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/", seen
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def link_to(address, token="tok"):
    return LibraryLink(ServerRecord.new(address, token, "1"), 1, "1")


FILES = [OpenFile("/a/one.tla", True), OpenFile("/a/two.tla", False)]
FILES_JSON = [
    {"path": "/a/one.tla", "unsaved": True},
    {"path": "/a/two.tla", "unsaved": False},
]


def test_register_sends_pid_and_files_and_parses_the_lease():
    lease = {"window": "w1", "poll_seconds": 2, "lease_seconds": 15}
    with recording_server("tok", {("POST", "/api/windows"): (200, lease)}) as (
        address,
        seen,
    ):
        got = link_to(address).register(42, FILES)
    assert got == WindowLease("w1", 2.0, 15.0)
    assert seen == [
        {
            "method": "POST",
            "path": "/api/windows",
            "body": {"pid": 42, "files": FILES_JSON},
            "auth": "Bearer tok",
        }
    ]


def test_sync_sends_the_list_and_parses_events_skipping_unknown_kinds():
    events = [
        {
            "seq": 3,
            "type": "changed-by-edit",
            "path": "/a/one.tla",
            "corpus": "c",
            "entry": "e1",
        },
        {"seq": 4, "type": "something-newer", "path": "/a/one.tla"},
    ]
    path = "/api/windows/w%2F1/sync"
    with recording_server("tok", {("POST", path): (200, {"events": events})}) as (
        address,
        seen,
    ):
        got = link_to(address).sync("w/1", FILES)
    assert got == [ChangedByEdit(3, "/a/one.tla", "c", "e1")]
    assert seen[0]["method"] == "POST" and seen[0]["path"] == path
    assert seen[0]["body"] == {"files": FILES_JSON}
    assert seen[0]["auth"] == "Bearer tok"


def test_saved_and_close_send_their_messages():
    replies = {
        ("POST", "/api/windows/w1/saved"): (204, None),
        ("DELETE", "/api/windows/w1"): (204, None),
    }
    with recording_server("tok", replies) as (address, seen):
        link = link_to(address)
        assert link.saved("w1", "/a/one.tla") is None
        assert link.close("w1") is None
    assert [(s["method"], s["path"], s["body"]) for s in seen] == [
        ("POST", "/api/windows/w1/saved", {"path": "/a/one.tla"}),
        ("DELETE", "/api/windows/w1", None),
    ]


def test_a_forgotten_window_raises_for_sync_and_saved_but_not_close():
    with recording_server("tok", {}) as (address, _):
        link = link_to(address)
        with pytest.raises(WindowForgotten):
            link.sync("w1", FILES)
        with pytest.raises(WindowForgotten):
            link.saved("w1", "/a/one.tla")
        link.close("w1")


def test_other_error_statuses_raise_os_error_naming_status_and_error():
    replies = {
        ("POST", "/api/windows"): (400, {"error": "bad pid"}),
        ("POST", "/api/windows/w1/sync"): (500, {"error": "internal error"}),
        ("DELETE", "/api/windows/w1"): (500, None),
    }
    with recording_server("tok", replies) as (address, _):
        link = link_to(address)
        with pytest.raises(OSError, match="400.*bad pid"):
            link.register(1, [])
        with pytest.raises(OSError, match="500.*internal error"):
            link.sync("w1", [])
        with pytest.raises(OSError, match="500"):
            link.close("w1")


def test_a_refused_connection_is_an_os_error():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    link = link_to(f"http://127.0.0.1:{port}/")
    with pytest.raises(OSError):
        link.register(1, [])
    with pytest.raises(OSError):
        link.sync("w1", [])
