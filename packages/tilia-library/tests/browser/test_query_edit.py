from __future__ import annotations

import sys
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))

from fixture_backend import FixtureBackend  # noqa: E402
from serve_fixtures import make_corpora  # noqa: E402

from tilia_library.api import register_all  # noqa: E402
from tilia_library.previews import Previews  # noqa: E402
from tilia_library.server import LibraryServer  # noqa: E402

STATEMENT = 'a then b -> SET label = "X"'
K1, K2, K3, K4, K5 = (
    "f1:u1-u2",
    "f1:u2-u3",
    "f1:u4-u5",
    "f4:u7-u8",
    "f4:u8-u9",
)


class RecordingBackend(FixtureBackend):
    """Records the keys of each apply; a test can change what the plan says."""

    def __init__(self):
        super().__init__()
        self.applied = []
        self.new_label = "Transition"

    def plan(self, corpus, statement, skip_files):
        answer = super().plan(corpus, statement, skip_files)
        answer["plan"][0]["writes"][0]["new"] = self.new_label
        return answer

    def apply(self, corpus, plan, keys, skip_files):
        self.applied.append(set(keys))
        return super().apply(corpus, plan, keys, skip_files)


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


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
def clock():
    return Clock()


@pytest.fixture
def entry_url(tmp_path, backend, clock):
    server = LibraryServer(backend)
    register_all(
        server, make_corpora(tmp_path), previews=Previews(ttl=100.0, clock=clock)
    )
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
        and "Failed to load resource" not in m.text  # the 4xx answers under test
        and page.problems.append(m.text),
    )
    page.on("pageerror", lambda e: page.problems.append(str(e)))

    def accept(dialog):
        page.dialogs.append(dialog.message)
        dialog.accept() if page.accepting else dialog.dismiss()

    page.on("dialog", accept)
    page.goto(entry_url)
    page.wait_for_selector("#files-count")
    page.click('#tabs button[data-panel="query"]')
    page.wait_for_selector("#ql-box")
    yield page
    assert page.problems == []
    page.close()


def run(page, text=STATEMENT):
    page.fill("#ql-box", text)
    page.press("#ql-box", "Control+Enter")
    page.wait_for_selector(".ql-card")


def preview(page):
    run(page)
    page.click("#ql-preview")
    page.wait_for_selector(".run-pick")


def pick(page, key):
    return page.locator(f'.run-pick[data-key="{key}"]')


def line(page, key):
    return page.locator(".ql-run").filter(has=pick(page, key))


def test_the_bar_shows_the_action(page):
    assert page.locator("#ql-edit-bar").is_hidden()
    run(page, "a then b")
    assert page.locator("#ql-edit-bar").is_hidden()
    run(page)
    assert page.locator("#ql-edit-verb").inner_text() == "SET"
    assert page.locator("#ql-apply").is_disabled()
    assert page.locator("#ql-all").is_hidden()
    run(page, "a then b")
    assert page.locator("#ql-edit-bar").is_hidden()


def test_preview_draws_the_plan_on_the_results(page):
    preview(page)
    assert page.locator("input.run-pick").count() == 5
    assert pick(page, K1).is_checked() and pick(page, K2).is_checked()
    assert pick(page, K3).is_disabled() and not pick(page, K3).is_checked()
    assert (
        line(page, K1).locator(".plan-diff").inner_text() == "Überleitung → Transition"
    )
    assert line(page, K4).locator(".plan-diff").inner_text() == "Переход → Übergang"
    gone = line(page, K2).locator(".plan-diff")
    assert "plan-del" in gone.get_attribute("class")
    assert gone.inner_text() == "− μετάβαση"
    assert line(page, K5).locator(".plan-diff").inner_text() == "+ Coda"
    skipped = line(page, K3).locator(".plan-diff.plan-skip")
    assert skipped.inner_text() == "skipped: the file has unsaved changes in TiLiA"
    assert page.locator("#ql-edit-skipped li").inner_text() == "f2: unreadable"
    assert (
        page.locator("#ql-edit-summary").inner_text()
        == "5 matches, 4 writes in 2 files, 1 deletion · ticked: 4 writes in 2 files"
    )
    assert page.locator("#ql-apply").inner_text() == "Apply (4)"
    assert (
        page.locator("#ql-all").is_visible() and page.locator("#ql-none").is_visible()
    )
    first = page.locator(".ql-card").first
    assert first.locator(".card-pick").is_checked()
    assert first.locator(".seq-meta").inner_text() == "3 matches · 2/2 ticked"


def test_strips_show_the_ticked_writes(page):
    preview(page)
    first, second = page.locator(".ql-card").nth(0), page.locator(".ql-card").nth(1)
    first.scroll_into_view_if_needed()
    first.locator(".strip-block").first.wait_for()
    assert first.locator(".strip-block.plan-set").inner_text() == "Transition"
    assert first.locator(".strip-block.plan-del").inner_text() == "μετάβαση"
    second.scroll_into_view_if_needed()
    second.locator(".strip-block").first.wait_for()
    add = second.locator(".strip-block.plan-add")
    assert add.inner_text() == "Coda"
    assert add.locator("xpath=ancestor::div[@class='strip-row']/span").inner_text() == (
        "lv 2"
    )
    pick(page, K2).uncheck()
    page.wait_for_function(
        "() => document.querySelectorAll('.ql-card')[0].querySelectorAll('.strip-block.plan-del').length === 0"
    )


def test_unticking_a_line_changes_the_summary_and_apply(page):
    preview(page)
    pick(page, K2).uncheck()
    assert "run-off" in line(page, K2).get_attribute("class")
    assert page.locator("#ql-apply").inner_text() == "Apply (3)"
    assert (
        page.locator("#ql-edit-summary")
        .inner_text()
        .endswith("ticked: 3 writes in 2 files")
    )
    card = page.locator(".ql-card").first
    assert card.locator(".card-pick").evaluate("e => e.indeterminate")
    assert card.locator(".seq-meta").inner_text() == "3 matches · 1/2 ticked"
    page.click("#ql-none")
    assert page.locator("#ql-apply").is_disabled()
    assert page.locator("#ql-apply").inner_text() == "Apply"
    assert page.locator(".card-off").count() == 2
    page.click("#ql-all")
    assert page.locator("#ql-apply").inner_text() == "Apply (4)"
    page.locator(".card-pick").first.uncheck()
    assert page.locator("#ql-apply").inner_text() == "Apply (2)"


def test_the_table_has_an_edit_column(page):
    preview(page)
    page.check("#ql-table")
    assert page.locator("#ql-grid th").first.inner_text() == "edit"
    assert page.locator("#ql-grid tbody tr").count() == 5
    assert page.locator("#ql-grid .run-pick").count() == 5
    page.locator("#ql-grid .run-pick").nth(1).uncheck()
    assert page.locator("#ql-grid tr.run-off").count() == 1
    assert page.locator("#ql-apply").inner_text() == "Apply (3)"


def test_typing_ends_the_preview_but_keeps_the_ticks(page):
    preview(page)
    pick(page, K2).uncheck()
    page.fill("#ql-box", STATEMENT + " ")
    assert page.locator("#ql-apply").is_disabled()
    assert page.locator("#ql-edit-summary").inner_text() == ""
    page.wait_for_selector(".ql-card")
    assert page.locator(".run-pick").count() == 0
    page.click("#ql-preview")
    page.wait_for_selector(".run-pick")
    assert not pick(page, K2).is_checked()
    assert page.locator("#ql-apply").inner_text() == "Apply (3)"


def test_apply_sends_only_the_ticked_keys(page, backend):
    preview(page)
    pick(page, K2).uncheck()
    page.click("#ql-apply")
    page.wait_for_function(
        "() => document.querySelector('#ql-edit-result').textContent.includes('Wrote')"
    )
    assert backend.applied == [{K1, K4, K5}]
    assert page.locator("#ql-edit-result").inner_text() == "Wrote 2 files."
    assert page.dialogs == [
        f"Write 3 changes to 2 files?\n\n{STATEMENT}\n\nThis rewrites the .tla files on disk."
    ]
    assert page.locator("#ql-apply").is_disabled()
    page.wait_for_function("() => document.querySelectorAll('.run-pick').length === 0")
    assert page.locator(".ql-card").count() == 2


def test_the_confirmation_counts_deletions(page):
    preview(page)
    page.click("#ql-apply")
    page.wait_for_function(
        "() => document.querySelector('#ql-edit-result').textContent.includes('Wrote')"
    )
    assert page.dialogs[0].startswith(
        "Write 4 changes to 2 files?\n1 of them delete components.\n\n"
    )


def test_cancelling_the_confirmation_writes_nothing(page, backend):
    preview(page)
    page.accepting = False
    page.click("#ql-apply")
    page.wait_for_timeout(300)
    assert page.dialogs and backend.applied == []
    assert page.locator("#ql-apply").is_enabled()


def test_a_changed_plan_gives_the_new_preview_and_writes_nothing(page, backend):
    preview(page)
    pick(page, K2).uncheck()
    backend.new_label = "Something else"
    page.click("#ql-apply")
    page.wait_for_function(
        "() => document.querySelector('#ql-edit-result').textContent.includes('changed')"
    )
    assert page.locator("#ql-edit-result").inner_text() == (
        "The files changed since the preview. This is the new preview; nothing was written."
    )
    assert backend.applied == []
    assert (
        line(page, K1).locator(".plan-diff").inner_text()
        == "Überleitung → Something else"
    )
    assert not pick(page, K2).is_checked()
    assert page.locator("#ql-apply").inner_text() == "Apply (3)"


def test_an_expired_preview(page, clock):
    preview(page)
    clock.now = 101.0
    page.click("#ql-apply")
    page.wait_for_function(
        "() => document.querySelector('#ql-edit-result').textContent.includes('expired')"
    )
    assert page.locator("#ql-edit-result").inner_text() == (
        "The preview expired; preview again."
    )
    assert page.locator("#ql-apply").is_disabled()
    assert page.locator(".run-pick").count() == 0


def test_a_statement_that_does_not_parse(page):
    run(page)
    page.fill("#ql-box", STATEMENT + " error")
    page.press("#ql-box", "Control+Enter")
    page.wait_for_selector("#ql-error:not([hidden])")
    page.click("#ql-preview", force=True)
    page.wait_for_selector("#ql-marks mark.err")
    assert page.locator("#ql-marks mark.err").inner_text() == "error"
