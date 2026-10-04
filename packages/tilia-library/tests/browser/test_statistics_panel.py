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


def show(page, text="a then b", **options):
    page.click('#tabs button[data-panel="query"]')
    page.fill("#ql-box", text)
    page.click('#tabs button[data-panel="statistics"]')
    for selector, value in options.items():
        page.select_option(selector, value)
    page.click("#stats-run")


def test_empty_query_disables_the_button(page):
    page.fill("#ql-box", "")
    page.click('#tabs button[data-panel="statistics"]')
    assert "Write a query in the Query tab first." in page.inner_text(
        'section[data-panel="statistics"]'
    )
    assert page.is_disabled("#stats-run")


def test_four_tables_charts_and_scripts(page):
    show(page)
    page.wait_for_selector("section.stats-table canvas")
    names = page.locator("section.stats-table").evaluate_all(
        "els => els.map(e => e.dataset.table)"
    )
    assert names == ["counts", "durations", "positions", "transitions"]
    page.wait_for_function("() => document.querySelectorAll('canvas').length === 3")
    assert page.locator('section[data-table="transitions"] canvas').count() == 0
    assert page.locator('section[data-table="counts"] h3').inner_text() == "Counts"
    body = page.inner_text('section[data-table="counts"] table')
    for label in ("Überleitung", "μετάβαση", "过渡", "מעבר", "🎵"):
        assert label in body
    page.wait_for_function(
        "() => Object.keys(Chart.instances).length === 3", timeout=3000
    )
    assert page.problems == []


def test_two_keys_fold_and_series(page):
    show(page, **{"#stats-by": "category", "#stats-by2": "file"})
    page.check("#stats-fold")
    page.click("#stats-run")
    page.wait_for_selector("#stats-warnings li")
    assert page.inner_text("#stats-warnings") == "subtypes folded"
    heads = page.locator('section[data-table="counts"] th').all_inner_texts()
    assert heads == ["category", "file", "matches", "files"]
    page.wait_for_function(
        "() => Object.values(Chart.instances)[0].data.datasets.length === 2"
    )
    assert page.problems == []


def test_field_replaces_the_first_key(page):
    show(page)
    page.fill("#stats-field", "file.composer")
    page.click("#stats-run")
    page.wait_for_function(
        "() => document.querySelector('section[data-table=counts] th').textContent === 'file.composer'"
    )


def test_query_error_is_shown(page):
    show(page, "an error here")
    page.wait_for_function("() => document.querySelector('#stats-error').textContent")
    assert page.is_visible("#stats-error")
    assert page.locator("section.stats-table").count() == 0


def test_csv_button_downloads(page):
    show(page)
    page.wait_for_selector('section[data-table="counts"] .stats-csv')
    with page.expect_download() as download:
        page.click('section[data-table="counts"] .stats-csv')
    assert download.value.suggested_filename.endswith("-counts.csv")
