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


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


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
    page.on(
        "console",
        lambda m: m.type == "error"
        and "Failed to load resource" not in m.text  # the 4xx answers under test
        and page.problems.append(m.text),
    )
    page.on("pageerror", lambda e: page.problems.append(str(e)))
    page.goto(entry_url)
    page.wait_for_selector("#files-count")
    page.click('#tabs button[data-panel="categories"]')
    page.wait_for_selector("#cat-chips .chip")
    yield page
    assert page.problems == []
    page.close()


def chip(page, category):
    return page.locator(f'#cat-chips .chip[data-cat="{category}"]')


def wait_for_list(page):
    page.wait_for_function("() => !!document.querySelector('#cat-grid')")


def test_chips_show_counts_most_frequent_first(page):
    chips = page.locator("#cat-chips .chip[data-cat]")
    assert chips.count() == 15
    assert chip(page, "chorus").locator(".n").inner_text() == "20"
    assert chip(page, "bridge.modern").locator(".n").inner_text() == "5"
    assert page.locator("#cat-more").inner_text() == "+2 more"
    assert page.locator("#cat-mode").is_hidden()
    assert page.locator("#cat-clear").is_hidden()
    assert page.locator("#cat-edit").is_hidden()


def test_chips_are_grouped(page):
    groups = page.locator("#cat-chips .chip-group")
    names = groups.locator(".chip-group-name").all_inner_texts()
    assert names[:2] == ["form", "role"]
    form = groups.filter(has=page.locator(".chip-group-name", has_text="form"))
    assert form.locator('.chip[data-cat="bridge"]').count() == 1
    page.click("#cat-more")
    assert page.locator("#cat-more").inner_text() == "Fewer"
    assert page.locator("#cat-chips .chip[data-cat]").count() == 17
    other = page.locator(".chip-group", has_text="other")
    assert other.locator('.chip[data-cat="coda"]').count() == 1
    page.click("#cat-more")
    assert page.locator("#cat-chips .chip[data-cat]").count() == 15


def test_search_matches_letters_in_order(page):
    page.fill("#cat-search", "b r d")
    names = page.locator("#cat-chips .chip[data-cat]").evaluate_all(
        "els => els.map(e => e.dataset.cat)"
    )
    assert sorted(names) == ["bridge", "bridge.classic", "bridge.modern"]
    assert page.locator("#cat-more").count() == 0
    page.fill("#cat-search", "zzz")
    assert page.locator("#cat-chips").inner_text() == "No category matches “zzz”."
    page.fill("#cat-search", "μετ")
    assert chip(page, "μετάβαση").count() == 1


def test_fold_reloads_the_chips(page):
    assert chip(page, "bridge").locator(".n").inner_text() == "12"
    page.check("#cat-fold")
    page.wait_for_function(
        "() => document.querySelectorAll('#cat-chips .chip[data-cat=\"bridge.modern\"]').length === 0"
    )
    assert chip(page, "bridge").locator(".n").inner_text() == "20"


def test_clicking_selects_and_shows_the_components(page):
    chip(page, "bridge").click()
    wait_for_list(page)
    assert "active" in chip(page, "bridge").get_attribute("class")
    assert page.locator("#cat-statement code").inner_text() == "bridge"
    assert page.locator("#cat-count").inner_text() == "5 components · 2 files"
    assert page.locator("#cat-grid tbody tr").count() == 5
    assert page.locator("#cat-clear").is_visible()
    assert page.locator("#cat-edit").is_visible()
    chip(page, "chorus").click()
    page.wait_for_function(
        "() => document.querySelector('#cat-statement').textContent === 'chorus'"
    )
    assert page.locator("#cat-chips .chip.active").count() == 1
    chip(page, "chorus").click()
    assert page.locator("#cat-chips .chip.active").count() == 0
    assert page.locator("#cat-list").inner_text() == ""
    assert page.locator("#cat-edit").is_hidden()


def test_shift_click_adds_and_the_mode_appears(page):
    chip(page, "bridge").click()
    wait_for_list(page)
    chip(page, "chorus").click(modifiers=["Shift"])
    page.wait_for_function(
        "() => document.querySelector('#cat-statement').textContent === 'bridge OR chorus'"
    )
    assert page.locator("#cat-mode").is_visible()
    page.select_option("#cat-mode", "all")
    page.wait_for_function(
        "() => document.querySelector('#cat-statement').textContent === 'bridge/chorus'"
    )
    page.click("#cat-clear")
    assert page.locator("#cat-chips .chip.active").count() == 0
    assert page.locator("#cat-mode").is_hidden()


def test_a_category_that_is_not_a_word_is_refused(page):
    page.click("#cat-more")
    chip(page, "verse 2").click()
    page.wait_for_function(
        "() => document.querySelector('#cat-error').textContent !== ''"
    )
    assert page.locator("#cat-error").inner_text() == (
        "'verse 2' can't be written in the query language yet: "
        "a category in a query is one word"
    )
    assert page.locator("#cat-list").inner_text() == ""
    chip(page, "bridge").click()
    wait_for_list(page)
    assert page.locator("#cat-error").is_hidden()


def test_a_bad_edit_shows_its_error(page):
    chip(page, "bridge").click()
    wait_for_list(page)
    page.select_option("#cat-field", "color")
    page.fill("#cat-value", "red")
    page.click("#cat-preview")
    page.wait_for_function(
        "() => document.querySelector('#cat-error').textContent !== ''"
    )
    assert page.locator("#cat-error").inner_text() == "a colour is #rrggbb"
    assert page.locator('section[data-panel="categories"]').is_visible()


def test_the_edit_inputs_follow_the_operation(page):
    chip(page, "bridge").click()
    assert page.locator("#cat-value").is_visible()
    assert page.locator("#cat-pattern").is_hidden()
    page.select_option("#cat-op", "replace")
    assert page.locator("#cat-value").is_hidden()
    assert page.locator("#cat-pattern").get_attribute("placeholder") == (
        "regular expression"
    )
    assert page.locator("#cat-replacement").is_visible()


def test_preview_lands_on_the_query_tab(page):
    chip(page, "bridge").click()
    wait_for_list(page)
    page.fill("#cat-value", "Brücke")
    page.click("#cat-preview")
    page.wait_for_selector(".run-pick")
    assert page.locator('section[data-panel="query"]').is_visible()
    assert page.locator('section[data-panel="categories"]').is_hidden()
    assert page.input_value("#ql-box") == 'bridge -> SET label = "Brücke"'
    assert page.locator("#ql-edit-verb").inner_text() == "SET"
    assert page.locator("#ql-apply").is_enabled()
    assert page.locator("#ql-edit-summary").inner_text().startswith("5 matches")


def test_a_replace_is_previewed_too(page):
    chip(page, "bridge").click()
    page.select_option("#cat-op", "replace")
    page.fill("#cat-pattern", "a/b")
    page.fill("#cat-replacement", "c")
    page.click("#cat-preview")
    page.wait_for_selector(".run-pick")
    assert page.input_value("#ql-box") == (
        'bridge WHERE label ~ /^(.*?)a\\/b(.*)$/ -> SET label = "\\1c\\2"'
    )
