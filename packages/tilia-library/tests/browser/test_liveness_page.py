from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

SERVE = Path(__file__).resolve().parents[1] / "support" / "serve_fixtures.py"


@pytest.fixture
def entry_url():
    process = subprocess.Popen(
        [sys.executable, str(SERVE), "--change-after", "1"],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        yield process.stdout.readline().strip()
    finally:
        process.terminate()
        process.wait(10)
        process.stdout.close()


def test_notice_appears_and_rerun_hides_it(entry_url):
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
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
                "document.getElementById('status').textContent.includes('Rescanning')"
            )
            assert problems == []
        finally:
            browser.close()
