from __future__ import annotations

import pytest

sync_api = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="session")
def playwright():
    """One Playwright for the session (its sync API runs once per process)."""
    with sync_api.sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright):
    """One headless Chromium for the tests that need nothing special."""
    browser = playwright.chromium.launch()
    yield browser
    browser.close()
