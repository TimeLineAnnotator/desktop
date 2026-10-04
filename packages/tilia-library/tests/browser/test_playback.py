from __future__ import annotations

import sys
import time
import wave
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))

from fixture_backend import FixtureBackend  # noqa: E402
from serve_fixtures import make_corpora  # noqa: E402

from tilia_library.api import register_all  # noqa: E402
from tilia_library.launch import TiliaNotFound  # noqa: E402
from tilia_library.server import LibraryServer  # noqa: E402

YOUTUBE = "dQw4w9WgXcQ"


class PlaybackBackend(FixtureBackend):
    """A WAV for f1, YouTube for f4; every time in the matches is a quarter."""

    def __init__(self, wav: Path) -> None:
        super().__init__()
        self.wav = wav

    def run(self, *args, **kwargs):
        result = super().run(*args, **kwargs)
        for m in result["matches"]:
            for key in ("start", "end"):
                m[key] /= 4
            m["match_start"] = max(m["start"] - 0.5, 0.0)
            m["match_end"] = m["end"] + 0.5
            for unit in (u for slot in m["slots"] for u in slot):
                unit["start"] /= 4
                unit["end"] /= 4
        return result

    def media_of(self, corpus, file_id):
        if file_id == "f1":
            return {
                "kind": "local",
                "path": str(self.wav),
                "youtube_id": None,
                "length": 2.0,
                "reason": None,
            }
        if file_id == "f4":
            return {
                "kind": "youtube",
                "path": None,
                "youtube_id": YOUTUBE,
                "length": None,
                "reason": None,
            }
        return super().media_of(corpus, file_id)


class Opener:
    def __init__(self) -> None:
        self.opened: list[Path] = []
        self.error: Exception | None = None

    def __call__(self, path):
        self.opened.append(path)
        if self.error:
            raise self.error
        return "tilia-gui"


@pytest.fixture
def opener():
    return Opener()


@pytest.fixture
def entry_url(tmp_path, opener):
    wav = tmp_path / "piece.wav"
    with wave.open(str(wav), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b"\x00\x00" * 16000)  # two seconds of silence
    corpora = make_corpora(tmp_path)
    folder = corpora.last().path / "corpus"  # where files.json's paths point
    folder.mkdir()
    for name in ("Überleitung.tla", "Переход.tla"):
        (folder / name).write_text("{}", encoding="utf-8")
    server = LibraryServer(PlaybackBackend(wav))
    register_all(server, corpora, opener=opener)
    server.start()
    yield server.entry_url
    server.stop()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        yield browser
        browser.close()


@pytest.fixture
def page(browser, entry_url):
    page = browser.new_page()
    page.problems = []
    page.on("console", lambda m: m.type == "error" and page.problems.append(m.text))
    page.on("pageerror", lambda e: page.problems.append(str(e)))
    page.route(
        "https://www.youtube-nocookie.com/**",
        lambda route: route.fulfill(
            content_type="text/html", body="<!doctype html><p>player</p>"
        ),
    )
    page.goto(entry_url)
    page.wait_for_selector("#files-count")
    yield page
    assert page.problems == []
    page.close()


@pytest.fixture
def cards(page):
    page.click('#tabs button[data-panel="query"]')
    page.fill("#ql-box", "a then b")
    page.wait_for_selector(".ql-card")
    return page


def wait_for(page, expression, timeout=10.0):
    """Wait until a JavaScript expression is true.

    The page's CSP forbids ``eval``, which Playwright's own wait uses, so the
    page is asked from here instead.
    """
    deadline = time.monotonic() + timeout
    while not page.evaluate(f"(() => {{ {_body(expression)} }})()"):
        assert time.monotonic() < deadline, f"never true: {expression}"
        time.sleep(0.05)


def _body(expression):
    """An expression, or statements ending in an expression, as a return."""
    *statements, last = [part for part in expression.split(";") if part.strip()]
    return "".join(f"{part};" for part in statements) + f"return {last};"


def stream_url(page, file_id="f1"):
    cid = page.evaluate("new URLSearchParams(location.search).get('corpus')")
    if cid is None:
        cid = page.evaluate(
            "fetch('/api/library').then(r => r.json()).then(d => d.last_corpus)"
        )
    return f"/api/{cid}/media/{file_id}/stream"


def audio_time(page):
    return page.evaluate("document.getElementById('player-audio').currentTime")


def first_card(page):
    return page.locator('.ql-card[data-file-id="f1"]')


def test_double_click_on_a_unit_plays_its_slot(cards):
    page = cards
    assert page.locator("#player").count() == 0
    first_card(page).locator(".ql-run").first.locator(".ql-unit").nth(1).dblclick()
    page.wait_for_selector("#player:not([hidden])")
    wait_for(page, "document.getElementById('player-audio').currentTime > 1.1")
    audio = page.locator("#player-audio")
    assert audio.get_attribute("src") == stream_url(page)
    assert audio.get_attribute("controls") is None
    assert "Überleitung.tla · 0:01–0:02" in page.inner_text("#player-what")
    assert page.inner_text("#player-yt") == ""
    assert page.evaluate("getSelection().toString()") == ""


def test_a_unit_stops_at_its_end(cards):
    page = cards
    first_card(page).locator(".ql-run").first.locator(".ql-unit").first.dblclick()
    wait_for(
        page,
        "const a = document.getElementById('player-audio');"
        "a && a.currentTime > 0 && a.paused",
    )
    assert 1.1 <= audio_time(page) < 1.6
    assert page.inner_text("#player-toggle") == "Play"
    page.click("#player-toggle")
    wait_for(page, "document.getElementById('player-audio').currentTime > 1.7")


def test_double_click_elsewhere_on_a_line_plays_the_match(cards):
    page = cards
    line = first_card(page).locator(".ql-run").nth(1)
    line.locator(".ql-lane").last.dblclick()
    page.wait_for_selector("#player:not([hidden])")
    wait_for(page, "document.getElementById('player-audio').currentTime > 1.1")
    assert "0:01–0:03" in page.inner_text("#player-what")


def test_play_with_context_starts_at_match_start(cards):
    page = cards
    first_card(page).locator(".ql-run").nth(1).locator(".ql-play").click()
    page.wait_for_selector("#player:not([hidden])")
    assert first_card(page).locator(".ql-play").first.inner_text() == "▶"
    assert first_card(page).locator(".ql-play").first.get_attribute("title") == (
        "Play with context"
    )
    wait_for(
        page,
        "const t = document.getElementById('player-audio').currentTime;"
        "t >= 0.6 && t < 1.1",
    )
    assert page.inner_text("#player-toggle") == "Pause"
    page.click("#player-toggle")
    wait_for(page, "document.getElementById('player-toggle').textContent === 'Play'")
    assert page.evaluate("document.getElementById('player-audio').paused")


def test_stop_hides_the_bar(cards):
    page = cards
    first_card(page).locator(".ql-play").first.click()
    page.wait_for_selector("#player:not([hidden])")
    assert page.evaluate("document.body.classList.contains('player-on')")
    page.click("#player-stop")
    assert page.locator("#player").is_hidden()
    assert page.evaluate("document.getElementById('player-audio').paused")


def test_table_row_double_click_plays_the_match(cards):
    page = cards
    page.check("#ql-table")
    page.locator("#ql-grid tbody tr").nth(1).locator("td").nth(1).dblclick()
    page.wait_for_selector("#player:not([hidden])")
    wait_for(page, "document.getElementById('player-audio').currentTime > 1.1")
    assert "0:01–0:03" in page.inner_text("#player-what")


def test_youtube_media_makes_an_iframe_and_no_script(cards):
    page = cards
    page.locator('.ql-card[data-file-id="f4"] .ql-run').first.locator(".ql-unit").nth(
        1
    ).dblclick()
    page.wait_for_selector("#player-yt iframe")
    iframe = page.locator("#player-yt iframe")
    assert iframe.get_attribute("src") == (
        f"https://www.youtube-nocookie.com/embed/{YOUTUBE}"
        "?start=0&end=3&autoplay=1&rel=0"
    ) or iframe.get_attribute("src").startswith(
        f"https://www.youtube-nocookie.com/embed/{YOUTUBE}?start="
    )
    assert iframe.get_attribute("allow") == "autoplay; encrypted-media"
    assert iframe.get_attribute("referrerpolicy") == "strict-origin-when-cross-origin"
    assert iframe.get_attribute("title") == "YouTube player"
    link = page.locator("#player-yt-link")
    assert link.get_attribute("href").startswith(
        f"https://www.youtube.com/watch?v={YOUTUBE}&t="
    )
    assert link.get_attribute("target") == "_blank"
    assert link.get_attribute("rel") == "noopener noreferrer"
    assert link.inner_text().startswith("Open on YouTube at 0:")
    assert page.evaluate("document.getElementById('player-audio').paused")
    assert page.locator("script[src*='youtube']").count() == 0


def test_youtube_url_has_the_slot_in_seconds(cards):
    page = cards
    # f4's first match: $1 is 0 to 0.75 s, $2 is 0.75 to 1.75 s
    page.locator('.ql-card[data-file-id="f4"] .ql-run').first.locator(".ql-unit").nth(
        1
    ).dblclick()
    page.wait_for_selector("#player-yt iframe")
    assert page.locator("#player-yt iframe").get_attribute("src") == (
        f"https://www.youtube-nocookie.com/embed/{YOUTUBE}"
        "?start=0&end=2&autoplay=1&rel=0"
    )
    assert page.locator("#player-yt-link").get_attribute("href") == (
        f"https://www.youtube.com/watch?v={YOUTUBE}&t=0s"
    )


def test_switching_to_local_media_removes_the_frame(cards):
    page = cards
    page.locator('.ql-card[data-file-id="f4"] .ql-play').first.click()
    page.wait_for_selector("#player-yt iframe")
    first_card(page).locator(".ql-play").first.click()
    wait_for(page, "document.getElementById('player-audio').currentTime > 0")
    assert page.locator("#player-yt iframe").count() == 0


def test_a_file_without_media_says_why(cards, page):
    page.evaluate(
        "fetch('/api/media/f2').then(r => r.json())"
    )  # the fixture has an answer for f2: "the file is unreadable"
    page.evaluate(
        "import('/web/js/playback.js').then(m => m.play('f2', 'broken.tla', 0, 1))"
    )
    page.wait_for_selector("#player:not([hidden])")
    assert page.inner_text("#player-what") == (
        "No media for broken.tla: the file is unreadable."
    )


def test_media_that_fails_to_load_says_so(cards, page, tmp_path):
    Path(tmp_path / "piece.wav").write_bytes(b"not a wav at all")
    first_card(page).locator(".ql-play").first.click()
    wait_for(
        page,
        "document.getElementById('player-what').textContent.startsWith(\"Couldn't\")",
    )
    assert page.inner_text("#player-what") == (
        "Couldn't play the media of Überleitung.tla."
    )


def test_double_click_on_a_checkbox_or_button_does_nothing(cards):
    page = cards
    page.locator(".ql-card .ql-open").first.dblclick()
    page.wait_for_timeout(200)
    assert page.locator("#player").count() == 0


def test_open_in_tilia_from_a_card(cards, opener):
    page = cards
    first_card(page).locator(".ql-open").click()
    wait_for(
        page, "document.getElementById('status').textContent.startsWith('Opening')"
    )
    assert page.inner_text("#status") == "Opening Überleitung.tla in TiLiA…"
    assert [p.name for p in opener.opened] == ["Überleitung.tla"]


def test_open_in_tilia_when_it_is_not_found(cards, opener):
    page = cards
    opener.error = TiliaNotFound("no")
    first_card(page).locator(".ql-open").click()
    wait_for(page, "document.getElementById('status').textContent.startsWith('TiLiA')")
    assert page.inner_text("#status") == (
        "TiLiA wasn't found. Install TiLiA, or open the file from TiLiA."
    )
    assert page.get_attribute("#status", "class") == "error"
    # the browser logs every 5xx answer; this one is the point of the test
    assert page.problems == [
        "Failed to load resource: the server responded with a status of 503 "
        "(Service Unavailable)"
    ]
    page.problems.clear()


def test_open_in_tilia_from_the_files_panel(page, opener):
    assert page.locator(".files-open").count() == 2  # only the files that are "ok"
    page.locator('tr[data-file-id="f4"] .files-open').click()
    wait_for(
        page, "document.getElementById('status').textContent.startsWith('Opening')"
    )
    assert page.inner_text("#status") == "Opening Переход.tla in TiLiA…"
    assert [p.name for p in opener.opened] == ["Переход.tla"]
