from __future__ import annotations

import contextlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

SERVE = Path(__file__).resolve().parents[1] / "support" / "serve_fixtures.py"
RESCANNING = "Rescanning…"
STATE = re.compile(r"/api/[^/?]+/state$")
FILES = re.compile(r"/api/[^/?]+/files$")
LATE_LIBRARY = """{
    const fetch = window.fetch;
    window.fetch = (url, opts) => url === "/api/library"
        ? new Promise(done => setTimeout(done, 300)).then(() => fetch(url, opts))
        : fetch(url, opts);
}"""


@contextlib.contextmanager
def serve(*arguments):
    process = subprocess.Popen(
        [sys.executable, str(SERVE), *arguments],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        yield process.stdout.readline().strip()
    finally:
        process.terminate()
        process.wait(10)
        process.stdout.close()


@pytest.fixture
def entry_url():
    with serve("--change-after", "1") as url:
        yield url


@pytest.fixture
def fixture_url():
    with serve() as url:
        yield url


@pytest.fixture
def page(browser):
    page = browser.new_page()
    try:
        page.problems = []
        page.on("pageerror", lambda e: page.problems.append(str(e)))
        yield page
    finally:
        page.close()


class Liveness:
    """The page, with the corpus's state (and the files' generation) under the test's control.

    The page polls only when the test says so, so nothing it shows changes between
    two of the test's steps.
    """

    def __init__(self, page, url) -> None:
        self.page = page
        self.state = {
            "generation": 1,
            "scanning": False,
            "available": True,
            "files": None,
            "unreadable": None,
            "unavailable": None,
            "last_scan": None,
        }
        self.files_generation = 1
        self.polls = 0
        # The test asks for every poll itself (see ``poll``), never a timer.
        page.add_init_script("window.setInterval = () => 0;")
        # The library answers late, as it can on a slow machine, so the page is
        # still booting, with no files panel yet, when the wait below starts.
        page.add_init_script(LATE_LIBRARY)
        page.route(STATE, self._state)
        page.route(FILES, self._files)
        page.goto(url)
        # The files panel notes its generation in the same step as it fills the count;
        # the panel is built only once the library has answered.
        page.wait_for_function(
            "() => { const c = document.getElementById('files-count');"
            " return c !== null && c.textContent !== ''; }"
        )
        self.poll()

    def _state(self, route) -> None:
        self.polls += 1
        route.fulfill(content_type="application/json", body=json.dumps(self.state))

    def _files(self, route) -> None:
        response = route.fetch()
        data = response.json()
        data["generation"] = self.files_generation
        route.fulfill(response=response, body=json.dumps(data))

    def poll(self, **state) -> None:
        """Answer the page's polls with this state until it has taken one in.

        Polls run one at a time, so once a second poll has been asked for since
        the change, the first has been handled; answering the same state twice
        changes nothing more.
        """
        self.state.update(state)
        target = self.polls + 2
        deadline = time.monotonic() + 10
        while self.polls < target:
            assert time.monotonic() < deadline, "the page stopped polling"
            self.page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
            self.page.wait_for_timeout(20)

    def notice_shown(self) -> bool:
        return self.page.locator("#changed").is_visible()

    def status(self) -> str:
        return self.page.inner_text("#status")

    def status_class(self) -> str:
        return self.page.get_attribute("#status", "class") or ""

    def set_status(self, text: str) -> None:
        self.page.evaluate(
            "t => { const s = document.getElementById('status'); s.textContent = t; s.className = ''; }",
            text,
        )

    def rescan(self) -> None:
        self.page.click("#files-rescan")
        self.page.wait_for_function(
            "t => document.getElementById('status').textContent === t", arg=RESCANNING
        )

    def rerun_fails(self, message: str) -> None:
        self.page.evaluate(
            """async m => {
                const live = await import('/web/js/liveness.js');
                live.onRerun('files', async () => { throw new Error(m); });
            }""",
            message,
        )

    def rerun_reloads(self) -> None:
        self.page.evaluate(
            """async () => {
                const live = await import('/web/js/liveness.js');
                const files = await import('/web/js/files.js');
                live.onRerun('files', files.loadFiles);
            }"""
        )


@pytest.fixture
def live(page, fixture_url):
    live = Liveness(page, fixture_url)
    yield live
    assert page.problems == []


def test_notice_appears_and_rerun_hides_it(browser, entry_url):
    page = browser.new_page()
    try:
        problems = []
        page.on("pageerror", lambda e: problems.append(str(e)))
        page.goto(entry_url)
        page.wait_for_selector("#files-count")
        assert page.locator("#changed").is_hidden()
        page.locator("#changed").wait_for(state="visible", timeout=10_000)
        assert "Files changed" in page.inner_text("#changed")
        loads = []
        page.on("request", lambda r: "/files" in r.url and loads.append(r.url))
        page.click("#changed-rerun")
        page.locator("#changed").wait_for(state="hidden", timeout=5_000)
        page.wait_for_timeout(2_500)
        assert loads and page.locator("#changed").is_hidden()
        page.click("#files-rescan")
        page.wait_for_function(
            "() => document.getElementById('status').textContent.includes('Rescanning')"
        )
        assert problems == []
    finally:
        page.close()


def test_the_notice_shows_when_the_generation_moves(live):
    assert not live.notice_shown()
    live.poll(generation=2, last_scan="t1")
    assert live.notice_shown()


def test_a_failed_rerun_keeps_the_notice_and_shows_the_error(live):
    live.poll(generation=2, last_scan="t1")
    live.rerun_fails("reload failed")
    live.page.click("#changed-rerun")
    live.page.wait_for_function(
        "() => document.getElementById('status').textContent !== ''"
    )
    assert live.notice_shown()
    assert "reload failed" in live.status()
    assert live.status_class() == "error"


def test_a_rerun_that_works_hides_the_notice(live):
    live.poll(generation=2, last_scan="t1")
    live.rerun_fails("reload failed")
    live.page.click("#changed-rerun")
    live.page.wait_for_function(
        "() => document.getElementById('status').textContent !== ''"
    )
    assert live.notice_shown()
    live.files_generation = 2
    live.rerun_reloads()
    with live.page.expect_response(FILES):
        live.page.click("#changed-rerun")
    # Hidden by the re-run itself: no poll happens in between.
    live.page.locator("#changed").wait_for(state="hidden", timeout=5_000)
    live.poll()
    assert not live.notice_shown()


def test_rescanning_clears_when_the_scan_ends(live):
    live.poll(last_scan="t1")
    # Seen running, then not.
    live.rescan()
    live.poll(scanning=True)
    assert live.status() == RESCANNING
    live.poll(scanning=False)
    assert live.status() == ""
    # Too quick to be seen running: it stays until last_scan moves on.
    live.rescan()
    live.poll()
    assert live.status() == RESCANNING
    live.poll(last_scan="t2")
    assert live.status() == ""
    # Another message in the status bar is left alone.
    live.set_status("something else")
    live.poll(last_scan="t3")
    assert live.status() == "something else"
