"""``tilia library``, run in a subprocess with its own state folder."""

import http.server
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time

import pytest
from conftest import api
from support import command_runner

from tilia_core.library_link import PROTOCOL, ServerRecord, ping

RUNNING = "TiLiA Library is running at "
ALREADY = "TiLiA Library is already running at "


def wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.02)


def start_library(launch, env, *arguments):
    running = launch("--no-browser", *arguments)
    running.read_until(RUNNING)
    return running


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def browser_lines(env):
    return env.log.read_text().splitlines() if env.log.exists() else []


@pytest.fixture
def folder(tmp_path):
    path = tmp_path / "corpus"
    path.mkdir()
    (path / "a.tla").write_text("{}")
    return path


class TestArguments:
    def test_help_lists_the_options(self, env):
        code, out, _ = command_runner.run(env.state, env.log, "--help")
        assert code == 0
        assert "tilia library" in out
        assert set(re.findall(r"--[\w-]+", out)) == {"--help", "--port", "--no-browser"}

    def test_help_with_python_dash_m(self):
        result = subprocess.run(
            [sys.executable, "-m", "tilia_library", "--help"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        assert result.returncode == 0
        assert set(re.findall(r"--[\w-]+", result.stdout)) == {
            "--help",
            "--port",
            "--no-browser",
        }

    def test_unknown_option_exits_2(self, env):
        code, _, _ = command_runner.run(env.state, env.log, "--nope")
        assert code == 2

    def test_folder_that_is_not_a_folder(self, env, tmp_path):
        code, out, err = command_runner.run(env.state, env.log, str(tmp_path / "nope"))
        assert code == 1
        assert f"tilia library: {tmp_path / 'nope'} is not a folder" in err


class TestStarting:
    def test_prints_the_address_and_serves(self, env, launch, folder):
        running = launch("--no-browser", str(folder))
        line = running.read_until(RUNNING)
        record = env.record()
        assert line == f"{RUNNING}{record.address}?token={record.token}"
        assert re.fullmatch(r"http://127\.0\.0\.1:\d+/", record.address)
        running.read_until("Press Ctrl+C to stop it.")
        assert not browser_lines(env)
        assert ping(record) is not None
        status, body = api(record, "GET", "/api/library")
        assert status == 200
        [corpus] = body["corpora"]
        assert corpus["path"] == str(folder.resolve())
        assert body["last_corpus"] == corpus["id"]

    def test_opens_the_browser_on_a_page_without_the_token(self, env, launch):
        running = launch()
        running.read_until(RUNNING)
        wait_for(lambda: browser_lines(env))
        record = env.record()
        page = env.state / "open.html"
        assert browser_lines(env) == [page.as_uri()]
        assert record.token not in page.as_uri()
        text = page.read_text()
        assert f"{record.address}?token={record.token}" in text
        assert "<!doctype html>" in text
        if os.name == "posix":
            assert page.stat().st_mode & 0o777 == 0o600
        assert (env.state / "server.toml").exists()
        # Stopping with Ctrl+C cleans up after the run.
        assert running.stop() == 0
        assert not (env.state / "server.toml").exists()
        assert not page.exists()
        assert not (env.state / "start.lock").exists()

    def test_taken_port(self, env, launch):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen()
            taken = sock.getsockname()[1]
            running = launch("--no-browser", "--port", str(taken))
            running.read_until(RUNNING)
            port = int(env.record().address.rstrip("/").rsplit(":", 1)[1])
            assert port > taken

    def test_nothing_listed_without_a_folder(self, env, launch):
        lock = env.state / "start.lock"
        lock.write_text("1")
        old = time.time() - 100
        os.utime(lock, (old, old))  # an old lock doesn't stop a start
        start_library(launch, env)
        assert not lock.exists()
        status, body = api(env.record(), "GET", "/api/library")
        assert body == {
            "corpora": [],
            "last_corpus": None,
            "how_to_add": "tilia library FOLDER",
            "notices": [],
        }

    def test_without_a_folder_the_last_corpus_comes_back(self, env, launch, folder):
        start_library(launch, env, str(folder)).stop()
        first = start_library(launch, env)
        _, body = api(env.record(), "GET", "/api/library")
        assert [c["path"] for c in body["corpora"]] == [str(folder.resolve())]
        assert body["last_corpus"] == body["corpora"][0]["id"]
        first.stop()
        (folder / "a.tla").unlink()
        folder.rmdir()
        second = start_library(launch, env)
        _, body = api(env.record(), "GET", "/api/library")
        assert body["corpora"][0]["available"] is False
        second.stop()
        assert f"tilia library: {folder.resolve()} is missing" in second.stderr_text()

    def test_unreadable_library_file(self, env, launch):
        (env.state / "library.toml").write_bytes(b"= broken")
        running = start_library(launch, env)
        _, body = api(env.record(), "GET", "/api/library")
        [notice] = body["notices"]
        assert re.fullmatch(
            r"library\.toml couldn't be read; kept as library\.unreadable-[\w-]+\.toml"
            r", starting with no corpora",
            notice,
        )
        running.stop()
        assert notice in running.stderr_text()
        [kept] = env.state.glob("library.unreadable-*")
        assert kept.read_bytes() == b"= broken"


class TestStaleRecords:
    def test_records_nobody_answers_for_do_not_stop_a_start(self, env, launch):
        record = ServerRecord(
            protocol=PROTOCOL,
            library_version="0",
            instance="made-up",
            pid=1,
            address=f"http://127.0.0.1:{free_port()}/",
            token="x",
            started=ServerRecord.new("http://127.0.0.1:1/", "t", "0").started,
        )
        record.write(env.state / "server.toml")
        first = start_library(launch, env)
        assert env.record().instance != "made-up"
        before = env.record()
        first.kill()  # a crash leaves its record behind
        assert (env.state / "server.toml").exists()
        start_library(launch, env)
        assert env.record().instance != before.instance


class TestAnotherVersion:
    def test_refuses_to_start(self, env):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps(
                    {"instance": "theirs", "protocol": 2, "library_version": "9"}
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        fake = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=fake.serve_forever, daemon=True).start()
        try:
            address = f"http://127.0.0.1:{fake.server_port}/"
            ServerRecord(
                protocol=2,
                library_version="9",
                instance="theirs",
                pid=1,
                address=address,
                token="x",
                started=ServerRecord.new(address, "t", "0").started,
            ).write(env.state / "server.toml")
            code, out, err = command_runner.run(env.state, env.log, "--no-browser")
        finally:
            fake.shutdown()
            fake.server_close()
        assert code == 1
        assert (
            f"Another version of TiLiA Library is running ({address}). "
            "Stop it with Ctrl+C in its terminal, then try again." in err
        )


class TestHandOver:
    def test_second_command_uses_the_first(self, env, launch, folder, tmp_path):
        other = tmp_path / "other"
        other.mkdir()
        start_library(launch, env, str(folder))
        record = env.record()
        code, out, err = command_runner.run(env.state, env.log, str(other))
        assert code == 0, err
        assert out.startswith(f"{ALREADY}{record.address}?token=")
        _, body = api(record, "GET", "/api/library")
        assert [c["path"] for c in body["corpora"]] == [
            str(folder.resolve()),
            str(other.resolve()),
        ]
        last = next(c for c in body["corpora"] if c["id"] == body["last_corpus"])
        assert last["path"] == str(other.resolve())
        assert browser_lines(env) == [(env.state / "open.html").as_uri()]
        assert env.record().instance == record.instance

    def test_two_started_together(self, env, launch):
        first = launch("--no-browser")
        second = launch("--no-browser")
        lines = [
            first.read_until("TiLiA Library is", timeout=15),
            second.read_until("TiLiA Library is", timeout=15),
        ]
        assert sorted(line.startswith(RUNNING) for line in lines) == [False, True]
        winner, loser = (
            (first, second) if lines[0].startswith(RUNNING) else (second, first)
        )
        assert loser.wait() == 0
        assert len(list(env.state.glob("server.toml"))) == 1
        assert winner.stop() == 0
