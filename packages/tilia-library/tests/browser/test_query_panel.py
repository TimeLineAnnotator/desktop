from __future__ import annotations

import sys
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))

from fixture_backend import FixtureBackend  # noqa: E402
from serve_fixtures import make_corpora  # noqa: E402

from tilia_library.api import register_all  # noqa: E402
from tilia_library.server import LibraryServer  # noqa: E402


@pytest.fixture
def entry_url(tmp_path):
    server = LibraryServer(FixtureBackend())
    register_all(server, make_corpora(tmp_path))
    server.start()
    yield server.entry_url
    server.stop()


class ChangingBackend(FixtureBackend):
    """Answers with a generation and a first label the test can change."""

    def __init__(self):
        super().__init__()
        self.gen = 1
        self.label = "before"

    def run(self, *args, **kwargs):
        result = super().run(*args, **kwargs)
        result["generation"] = self.gen
        return result

    def context(self, corpus, file_id, timeline_ids):
        result = super().context(corpus, file_id, timeline_ids)
        result["timelines"][0]["components"][0]["label"] = self.label
        return result


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser, entry_url):
    page = browser.new_page()
    page.problems = []
    page.on("console", lambda m: m.type == "error" and page.problems.append(m.text))
    page.on("pageerror", lambda e: page.problems.append(str(e)))
    page.goto(entry_url)
    page.wait_for_selector("#files-count")
    page.click('#tabs button[data-panel="query"]')
    page.wait_for_selector("#ql-box")
    yield page
    page.close()


def run(page, text):
    page.fill("#ql-box", text)
    page.press("#ql-box", "Control+Enter")


def test_typing_runs_after_a_pause_and_draws_cards(page):
    page.fill("#ql-box", "a then b")
    page.wait_for_selector(".ql-card")
    assert page.locator(".ql-card").count() == 2
    assert page.locator("#ql-count").inner_text() == "5 matches · 2 files"
    assert page.locator("#ql-explain").inner_text() != ""
    assert page.locator("#ql-stopped").is_hidden()
    assert page.locator("#ql-warnings").is_hidden()
    first = page.locator(".ql-card").first
    assert first.get_attribute("data-file-id")
    assert "Überleitung.tla" in first.inner_text()
    assert "$1" in first.locator(".ql-run").first.inner_text()


def test_strips_are_drawn_with_the_matched_blocks(page):
    run(page, "a then b")
    page.wait_for_selector(".ql-card .strip-block")
    card = page.locator(".ql-card").first
    assert card.locator(".strip-block.matched:not(.matched-parent)").count() >= 1
    assert card.locator(".strip-block.matched-ctx").count() >= 1
    style = card.locator(".strip-block").first.get_attribute("style")
    assert "background:#" in style


def test_table_and_csv(page):
    run(page, "a then b")
    page.wait_for_selector(".ql-card")
    page.check("#ql-table")
    assert page.locator("#ql-grid tbody tr").count() == 5
    assert page.locator("#ql-grid th").first.inner_text() == "file"
    with page.expect_download() as download:
        page.click("#ql-csv")
    assert download.value.suggested_filename.endswith("-query.csv")
    text = Path(download.value.path()).read_text(encoding="utf8")
    assert text.startswith("file,title,timeline,")
    assert "\r" not in text and "﻿" not in text
    assert ",0.000,9.000," in text


def test_error_is_marked_after_an_emoji(page):
    run(page, "a then b")
    page.wait_for_selector(".ql-card")
    run(page, "😀 error")
    page.wait_for_selector("#ql-error:not([hidden])")
    assert page.locator("#ql-marks mark.err").inner_text() == "error"
    assert page.locator("#ql-results.stale").count() == 1
    assert page.locator(".ql-card").count() == 2
    run(page, "a then b")
    page.wait_for_selector("#ql-error", state="hidden")
    assert page.locator("#ql-marks mark.err").count() == 0
    assert page.locator("#ql-results.stale").count() == 0


def test_emptying_the_box_clears_results(page):
    run(page, "a then b")
    page.wait_for_selector(".ql-card")
    run(page, "")
    page.wait_for_function("document.querySelectorAll('.ql-card').length === 0")
    assert page.locator("#ql-count").inner_text() == ""
    assert page.locator("#ql-csv").is_disabled()


def test_show_sql_and_run_sql(page):
    run(page, "a then b")
    page.wait_for_selector(".ql-card")
    page.click("#ql-show-sql")
    page.wait_for_selector("#ql-sql:not([hidden])")
    assert page.input_value("#ql-sql-box").startswith("SELECT")
    assert page.locator("#ql-sql-notes li").count() == 1
    page.click("#ql-sql-run")
    page.wait_for_selector("#ql-sql-result table")
    assert page.locator("#ql-sql-result tbody tr").count() == 4
    page.fill("#ql-sql-box", "DELETE FROM units")
    page.click("#ql-sql-run")
    page.wait_for_function("document.querySelector('#ql-sql-error').textContent !== ''")
    assert "SELECT" in page.locator("#ql-sql-error").inner_text()


def test_text_is_remembered_per_corpus(page):
    page.fill("#ql-box", "remember me")
    page.reload()
    page.click('#tabs button[data-panel="query"]')
    page.wait_for_selector("#ql-box")
    assert page.input_value("#ql-box") == "remember me"


def test_strips_are_redrawn_from_fresh_contexts_after_the_files_change(
    browser, tmp_path
):
    backend = ChangingBackend()
    server = LibraryServer(backend)
    register_all(server, make_corpora(tmp_path))
    server.start()
    page = browser.new_page()
    try:
        page.goto(server.entry_url)
        page.wait_for_selector("#files-count")
        page.click('#tabs button[data-panel="query"]')
        page.wait_for_selector("#ql-box")
        run(page, "a then b")
        page.wait_for_selector(".strip-block:has-text('before')")
        backend.label = "after"
        backend.gen = 2
        run(page, "a then b")
        page.wait_for_selector(".strip-block:has-text('after')", timeout=3000)
    finally:
        page.close()
        server.stop()
