from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))

from fixture_backend import FixtureBackend  # noqa: E402
from serve_fixtures import make_corpora  # noqa: E402

from tilia_library.api import register_all  # noqa: E402
from tilia_library.server import LibraryServer  # noqa: E402

FILES = json.loads(
    (Path(__file__).resolve().parents[1] / "support/fixtures/files.json").read_text(
        encoding="utf8"
    )
)


@pytest.fixture
def entry_url(tmp_path):
    server = LibraryServer(FixtureBackend())
    register_all(server, make_corpora(tmp_path))
    server.start()
    yield server.entry_url
    server.stop()


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
    yield page
    page.close()


def names(page):
    return page.locator(
        "tr[data-file-id]:not(.detail) td:nth-child(2)"
    ).all_inner_texts()


def test_boots_cleanly(page):
    assert page.evaluate("window.__bootOk") is True
    assert page.problems == []
    assert page.locator("#tabs button").count() == 5


def test_picker(page):
    options = page.locator("#corpus-pick option").all_inner_texts()
    assert options == ["Fixture corpus", "Zweites Korpus", "Verschwunden (unavailable)"]


def test_files_table(page):
    assert page.inner_text("#files-count") == f"{len(FILES)} files"
    assert names(page) == [f["name"] for f in FILES]
    body = page.inner_text("tbody")
    for label in ("μετάβαση", "过渡", "מעבר", "can't read"):
        assert label in body


def test_sort_filter_expand(page):
    page.click("th[data-sort=name]")
    first = names(page)
    page.click("th[data-sort=name]")
    assert names(page) == first[::-1]
    page.fill("#files-filter", "מעבר")
    assert page.inner_text("#files-count") == f"1 of {len(FILES)} files"
    page.click("button.expand")
    page.wait_for_selector("tr.detail tbody tr")
    assert page.locator("tr.detail tbody tr").count() == 3
    assert "hierarchy" in page.inner_text("tr.detail")


def test_query_tab_and_remove(page):
    page.click("#tabs button[data-panel=query]")
    assert page.is_visible("#ql-box")
    page.once("dialog", lambda d: d.accept())
    page.click("#corpus-remove")
    page.wait_for_function(
        "() => document.querySelectorAll('#corpus-pick option').length === 2"
    )
    assert "Fixture corpus" not in page.locator("#corpus-pick option").all_inner_texts()
