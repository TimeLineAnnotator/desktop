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


class RecordingBackend(FixtureBackend):
    def __init__(self):
        super().__init__()
        self.undone = []

    def undo(self, corpus, entry, skip_files):
        self.undone.append(entry)
        return super().undo(corpus, entry, skip_files)


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def backend():
    return RecordingBackend()


@pytest.fixture
def entry_url(tmp_path, backend):
    server = LibraryServer(backend)
    register_all(server, make_corpora(tmp_path))
    server.start()
    yield server.entry_url
    server.stop()


@pytest.fixture
def page(browser, entry_url):
    page = browser.new_page()
    page.problems = []
    page.dialogs = []
    page.accepting = True
    page.on(
        "console",
        lambda m: m.type == "error"
        and "Failed to load resource" not in m.text
        and page.problems.append(m.text),
    )
    page.on("pageerror", lambda e: page.problems.append(str(e)))

    def answer(dialog):
        page.dialogs.append(dialog.message)
        dialog.accept() if page.accepting else dialog.dismiss()

    page.on("dialog", answer)
    page.goto(entry_url)
    page.wait_for_selector("#files-count")
    page.click('#tabs button[data-panel="edit-log"]')
    page.wait_for_selector(".edit-entry")
    yield page
    assert page.problems == []
    page.close()


def entry(page, name):
    return page.locator(f'.edit-entry[data-entry="{name}"]')


def test_entries_are_listed_newest_first(page):
    rows = page.locator(".edit-entry")
    assert rows.count() == 3
    assert [rows.nth(i).get_attribute("data-entry") for i in range(3)] == [
        "e3",
        "e2",
        "e1",
    ]
    first = entry(page, "e3")
    assert first.locator(".edit-statement").inner_text() == (
        'מעבר then Überleitung -> SET label = "Übergang"'
    )
    expected = page.evaluate("new Date('2026-03-02T09:30:00').toLocaleString()")
    assert first.locator(".edit-at").inner_text() == expected
    assert first.locator(".edit-files").inner_text() == (
        "2 files: Überleitung.tla, Переход.tla"
    )
    assert entry(page, "e1").locator(".edit-files").inner_text() == (
        "1 file: Überleitung.tla"
    )


def test_a_file_without_a_name_shows_its_id(page):
    text = entry(page, "e2").locator(".edit-files").inner_text()
    assert text == "2 files: Переход.tla, f9"


def test_an_undone_entry_has_no_button(page):
    old = entry(page, "e1")
    assert old.locator(".edit-undone").inner_text() == "Undone"
    assert old.locator(".edit-undo").count() == 0
    assert entry(page, "e3").locator(".edit-undo").inner_text() == "Undo"


def test_undo_shows_what_was_restored_and_refused(page, backend):
    entry(page, "e3").locator(".edit-undo").click()
    page.wait_for_function(
        "() => document.querySelector('#edit-log-result').innerText.includes('Restored')"
    )
    assert page.dialogs == [
        'Undo this edit?\n\nמעבר then Überleitung -> SET label = "Übergang"'
        "\n\nFiles changed since the edit are left as they are."
    ]
    assert backend.undone == ["e3"]
    result = page.locator("#edit-log-result")
    assert "Restored 1 file." in result.inner_text()
    assert "Not restored, changed since the edit:" in result.inner_text()
    assert [t for t in result.locator("li").all_inner_texts()] == [
        "Переход.tla: edited in TiLiA after this edit: 2 labels"
    ]


def test_dismissing_the_dialog_sends_nothing(page, backend):
    page.accepting = False
    entry(page, "e3").locator(".edit-undo").click()
    page.wait_for_timeout(300)
    assert len(page.dialogs) == 1
    assert backend.undone == []
    assert page.locator("#edit-log-result").inner_text() == ""
