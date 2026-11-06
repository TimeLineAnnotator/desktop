"""How the page gets the token, keeps it, and loses it, in a real browser."""

from __future__ import annotations

import logging
import re
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))

from fixture_backend import FixtureBackend  # noqa: E402
from serve_fixtures import make_corpora  # noqa: E402

from tilia_library.api import register_all  # noqa: E402
from tilia_library.command import write_open_page  # noqa: E402
from tilia_library.server import LibraryServer  # noqa: E402

SERVE = Path(__file__).resolve().parents[1] / "support" / "serve_fixtures.py"
STORED = "sessionStorage.getItem('tilia-library.token')"


@pytest.fixture
def server(tmp_path):
    server = LibraryServer(FixtureBackend())
    register_all(server, make_corpora(tmp_path))
    server.start()
    yield server
    server.stop()


@pytest.fixture
def context(browser):
    context = browser.new_context()
    yield context
    context.close()


def open_page(context, url):
    page = context.new_page()
    page.problems = []
    page.on("console", lambda m: m.type == "error" and page.problems.append(m.text))
    page.on("pageerror", lambda e: page.problems.append(str(e)))
    page.goto(url)
    return page


def shows_the_library(page):
    page.wait_for_selector("#files-count")
    assert page.locator("#locked").count() == 0 or page.is_hidden("#locked")
    return True


def says_how_to_open(page):
    page.wait_for_selector("#locked")
    text = page.inner_text("body")
    assert "This address can't be opened directly" in text
    assert "tilia library" in text
    assert page.locator("#tabs").count() == 0
    return True


def test_the_entry_cleans_the_address_and_sets_no_cookie(context, server):
    page = open_page(context, server.entry_url)
    assert shows_the_library(page)
    assert page.url == server.address
    assert server.token not in page.url
    assert context.cookies() == []
    assert page.evaluate("document.cookie") == ""
    assert page.evaluate(STORED) == server.token
    assert page.problems == []


def test_the_token_stays_out_of_addresses_logs_and_referers(context, server, caplog):
    page = context.new_page()
    requests = []
    page.on("request", lambda r: requests.append(r))
    with caplog.at_level(logging.DEBUG):
        page.goto(server.entry_url)
        assert shows_the_library(page)
        page.click('#tabs button[data-panel="query"]')
        page.wait_for_selector("#ql-box")
    assert caplog.records
    for record in caplog.records:
        assert server.token not in record.getMessage()
    api = [r for r in requests if "/api/" in r.url]
    assert api
    for request in requests:
        assert server.token not in request.url.partition("#")[0]
        assert "referer" not in request.all_headers()
    for request in api:
        assert request.all_headers()["authorization"] == f"Bearer {server.token}"
    for request in requests:
        if "/api/" not in request.url:
            assert "authorization" not in request.all_headers()


def test_the_back_button_does_not_bring_the_token_back(context, server):
    page = open_page(context, "about:blank")
    page.goto(server.entry_url)
    assert shows_the_library(page)
    page.go_back()
    assert page.url == "about:blank"
    page.go_forward()
    assert shows_the_library(page)
    assert page.url == server.address


def test_the_page_the_command_opens_leads_to_the_library(context, server, tmp_path):
    opener = tmp_path / "open.html"
    write_open_page(opener, server.entry_url)
    page = open_page(context, opener.as_uri())
    page.wait_for_url(server.address)
    assert shows_the_library(page)
    assert context.cookies() == []
    assert page.problems == []


def test_a_reload_keeps_working(context, server):
    page = open_page(context, server.entry_url)
    assert shows_the_library(page)
    page.reload()
    assert shows_the_library(page)
    page.reload()
    assert shows_the_library(page)
    assert page.url == server.address
    assert page.problems == []


def test_moving_to_another_corpus_keeps_working(context, server):
    page = open_page(context, server.entry_url)
    assert shows_the_library(page)
    page.select_option("#corpus-pick", label="Zweites Korpus")
    page.wait_for_url(re.compile(r"corpus="))
    assert shows_the_library(page)
    assert "Zweites Korpus" in page.locator("#corpus-path").inner_text()
    assert page.problems == []


def test_a_second_tab_from_the_entry_address_works_on_its_own(context, server):
    first = open_page(context, server.entry_url)
    second = open_page(context, server.entry_url)
    assert shows_the_library(first)
    assert shows_the_library(second)
    first.close()
    second.reload()
    assert shows_the_library(second)
    assert second.problems == []


def test_a_new_tab_on_the_bare_address_says_how_to_open_the_library(context, server):
    first = open_page(context, server.entry_url)
    assert shows_the_library(first)
    second = context.new_page()
    second.problems = []
    asked = []
    second.on("request", lambda r: "/api/" in r.url and asked.append(r.url))
    second.goto(server.address)
    assert says_how_to_open(second)
    assert asked == []
    assert second.evaluate(STORED) is None


def test_a_tab_opened_from_the_page_inherits_the_token(context, server):
    # What "duplicate tab" does too: the browser copies the tab's sessionStorage.
    page = open_page(context, server.entry_url)
    assert shows_the_library(page)
    with context.expect_page() as opened:
        page.evaluate("window.open(location.href); undefined")
    assert shows_the_library(opened.value)


def test_the_entry_address_opened_on_the_bare_address_loads_the_library(
    context, server
):
    # Only the fragment differs, so this doesn't load the page by itself.
    page = open_page(context, server.address)
    assert says_how_to_open(page)
    page.goto(server.entry_url)
    assert shows_the_library(page)
    assert page.url == server.address
    assert page.evaluate(STORED) == server.token


def test_a_wrong_token_says_how_to_open_the_library(context, server):
    page = open_page(context, f"{server.address}#token=wrong")
    assert says_how_to_open(page)
    assert page.url == server.address
    assert page.evaluate(STORED) is None


def test_an_old_entry_address_says_how_to_open_the_library(context, server):
    page = open_page(context, f"{server.address}?token={server.token}")
    assert says_how_to_open(page)
    assert context.cookies() == []


# A real restart: a server stopped in this process would keep answering on the
# connections the browser holds.
def start_serving(*args):
    process = subprocess.Popen(
        [sys.executable, str(SERVE), *args], stdout=subprocess.PIPE, text=True
    )
    return process, process.stdout.readline().strip()


def stop_serving(process):
    process.kill()
    process.wait(10)
    process.stdout.close()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_a_restart_with_a_new_token(context):
    port = str(free_port())
    process, entry = start_serving("--port", port)
    try:
        address, _, _ = entry.partition("#")
        page = open_page(context, entry)
        assert shows_the_library(page)
    finally:
        stop_serving(process)
    process, new_entry = start_serving("--port", port)
    try:
        assert new_entry.startswith(address) and new_entry != entry
        # A tab left open says so when it next asks for something, as it did
        # with a cookie; the next load says how to open the library.
        page.click('#tabs button[data-panel="edit-log"]')
        page.wait_for_function(
            "() => document.getElementById('status').textContent"
            ".includes('missing or wrong credentials')"
        )
        page.reload()
        assert says_how_to_open(page)
        assert page.evaluate(STORED) is None
        page.goto(new_entry)
        assert shows_the_library(page)
        page.reload()
        assert shows_the_library(page)
    finally:
        stop_serving(process)


class Neighbour(BaseHTTPRequestHandler):
    """Another program's server on 127.0.0.1: the one a cookie would reach."""

    seen: list = []

    def do_GET(self):
        type(self).seen.append((self.path, dict(self.headers)))
        body = b"<!doctype html><title>neighbour</title>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


@pytest.fixture
def neighbour():
    Neighbour.seen = []
    httpd = HTTPServer(("127.0.0.1", 0), Neighbour)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/"
    httpd.shutdown()
    httpd.server_close()


def test_another_local_server_gets_nothing(context, server, neighbour):
    page = open_page(context, server.entry_url)
    assert shows_the_library(page)
    assert page.evaluate(STORED) == server.token

    other = context.new_page()
    other.goto(neighbour)
    page.goto(neighbour)  # the same tab too, where sessionStorage lasts
    assert Neighbour.seen
    for _, headers in Neighbour.seen:
        names = {name.lower() for name in headers}
        assert "cookie" not in names
        assert "referer" not in names
        assert server.token not in str(headers)
    for tab in (other, page):
        assert tab.evaluate("sessionStorage.length") == 0
        assert tab.evaluate("document.cookie") == ""


@pytest.mark.parametrize("path", ["web/js/main.js", "api/ping"])
def test_another_local_page_cannot_load_anything_from_the_library(
    context, server, neighbour, path
):
    # Cross-Origin-Resource-Policy: the public code included.
    page = open_page(context, server.entry_url)
    assert shows_the_library(page)
    other = context.new_page()
    other.goto(neighbour)
    outcome = other.evaluate(
        "url => fetch(url, { mode: 'no-cors', credentials: 'include' })"
        ".then(() => 'answered', () => 'blocked')",
        f"{server.address}{path}",
    )
    assert outcome == "blocked"
