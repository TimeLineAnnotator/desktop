from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

SERVE = Path(__file__).resolve().parents[1] / "support" / "serve_fixtures.py"
PANELS = ("files", "query", "categories", "statistics", "edit-log")
COLLATED = (
    "(names) => names.slice().sort("
    'new Intl.Collator(undefined, { numeric: true, sensitivity: "base" }).compare)'
)
# the scripts the fixture query's labels are written in
# (the fixture query's answer has no emoji; the files table does)
SCRIPTS = ("Überleitung", "transição", "μετάβαση", "过渡", "מעבר")


def serve(*args):
    process = subprocess.Popen(
        [sys.executable, str(SERVE), *args], stdout=subprocess.PIPE, text=True
    )
    try:
        yield process.stdout.readline().strip()
    finally:
        process.terminate()
        process.wait(10)
        process.stdout.close()


@pytest.fixture(scope="module")
def entry_url():
    yield from serve()


@pytest.fixture
def changing_url():
    yield from serve("--change-after", "1")


def new_page(browser, url):
    page = browser.new_page()
    page.problems = []
    page.foreign = []
    page.on("console", lambda m: m.type == "error" and page.problems.append(m.text))
    page.on("pageerror", lambda e: page.problems.append(str(e)))
    page.on("request", lambda r: page.foreign.append(r.url))
    page.goto(url)
    page.wait_for_selector("#files-count")
    return page


@pytest.fixture
def page(browser, entry_url):
    page = new_page(browser, entry_url)
    yield page
    page.close()
    assert page.problems == []


def open_panel(page, name):
    page.click(f'#tabs button[data-panel="{name}"]')
    page.wait_for_selector(f'section.panel[data-panel="{name}"]:not([hidden])')


def run_query(page, text="a then b"):
    open_panel(page, "query")
    page.fill("#ql-box", text)
    page.press("#ql-box", "Control+Enter")
    page.check("#ql-table")
    page.wait_for_selector("#ql-grid tbody tr")


def files_names(page):
    return page.eval_on_selector_all(
        "section.panel[data-panel=files] tbody > tr[data-file-id] td:nth-child(2)",
        "cells => cells.map(c => c.textContent)",
    )


def grid_column(page, col):
    index = page.eval_on_selector_all(
        "#ql-grid th button.ql-sort",
        "(b, c) => b.findIndex(x => x.dataset.col === c)",
        col,
    )
    return page.eval_on_selector_all(
        "#ql-grid tbody tr",
        "(rows, i) => rows.map(r => r.children[i].textContent)",
        index,
    )


def test_each_panel_opens_and_shows_its_content(page):
    for name in PANELS:
        open_panel(page, name)
        section = page.locator(f'section.panel[data-panel="{name}"]')
        page.wait_for_function(
            '(n) => document.querySelector(`section.panel[data-panel="${n}"]`)'
            ".textContent.trim() !== ''",
            arg=name,
        )
        assert section.inner_text().strip() != ""
        assert "Not available yet" not in section.inner_text()


def test_files_table_shows_the_scripts_and_sorts_like_the_collator(page):
    text = page.inner_text("section.panel[data-panel=files]")
    for word in ("Überleitung", "μετάβαση", "מעבר", "🎵", "Переход"):
        assert word in text
    names = files_names(page)
    assert len(names) >= 4
    expected = page.evaluate(COLLATED, names)
    page.click('th[data-sort="name"]')
    assert files_names(page) == expected
    page.click('th[data-sort="name"]')
    assert files_names(page) == expected[::-1]


@pytest.mark.parametrize(
    "fragment, name",
    [
        ("μετάβ", "Überleitung.tla"),
        ("מעב", "Überleitung.tla"),
        ("🎵", "Überleitung.tla"),
    ],
)
def test_files_filter_finds_the_file(page, fragment, name):
    page.fill("#files-filter", fragment)
    page.wait_for_function(
        "() => document.getElementById('files-count').textContent.startsWith('1 of')"
    )
    assert files_names(page) == [name]


def test_query_table_shows_the_scripts_and_sorts_like_the_collator(page):
    run_query(page)
    text = page.inner_text("#ql-grid")
    for word in SCRIPTS:
        assert word in text
    column = grid_column(page, "label")
    expected = page.evaluate(COLLATED, column)
    page.click('#ql-grid th button[data-col="label"]')
    assert grid_column(page, "label") == expected
    assert "▲" in page.inner_text('#ql-grid th button[data-col="label"]')
    page.click('#ql-grid th button[data-col="label"]')
    assert grid_column(page, "label") == expected[::-1]
    assert "▼" in page.inner_text('#ql-grid th button[data-col="label"]')


def test_query_table_sorts_numbers_as_numbers_and_keeps_empties_last(page):
    run_query(page)
    for _ in range(2):
        page.click('#ql-grid th button[data-col="start"]')
        values = [float(v) for v in grid_column(page, "start")]
        assert values == sorted(values) or values == sorted(values, reverse=True)
    page.click('#ql-grid th button[data-col="bar"]')
    assert set(grid_column(page, "bar")) == {""}
    page.click('#ql-grid th button[data-col="start"]')
    page.click('#ql-grid th button[data-col="start"]')
    assert grid_column(page, "start") == sorted(
        grid_column(page, "start"), key=float, reverse=True
    )


def test_files_changed_notice_appears_and_rerun_clears_it(browser, changing_url):
    page = new_page(browser, changing_url)
    try:
        page.locator("#changed").wait_for(state="visible", timeout=10_000)
        assert "Files changed — re-run?" in page.inner_text("#changed")
        page.click("#changed-rerun")
        page.locator("#changed").wait_for(state="hidden", timeout=5_000)
        assert page.problems == []
    finally:
        page.close()


def test_nothing_leaves_the_machine(page):
    for name in PANELS:
        open_panel(page, name)
    run_query(page)
    page.wait_for_timeout(500)
    outside = [
        u
        for u in page.foreign
        if not u.startswith(("http://127.0.0.1", "data:", "blob:", "about:"))
    ]
    assert outside == []
