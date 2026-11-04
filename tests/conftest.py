"""Shared headless-Chromium fixtures for the guide and widget browser tests.

They skip if Chromium isn't installed (`python -m playwright install chromium`).
"""

import os

import pytest


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        try:
            chromium = pw.chromium.launch()
        except Exception as exc:  # browser binaries not installed
            # CI installs Chromium; a broken install step must fail, not
            # silently skip every browser test.
            if os.environ.get("CI"):
                raise
            pytest.skip(f"Chromium unavailable: {exc}")
        yield chromium
        chromium.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    yield page
    page.close()
