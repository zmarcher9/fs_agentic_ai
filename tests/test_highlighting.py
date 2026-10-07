"""Tests for the live guide's highlighting and sidebar (playwright_guide/).

Browser tests run headless Chromium against a fixture page laid out like
FireMapSim's control bar; they skip if Chromium isn't installed
(`python -m playwright install chromium`).
"""

import os

import pytest

from playwright_guide.highlighting import (
    STEP_SELECTORS,
    detect_step,
    highlight_off,
    highlight_on,
    pick_highlight,
)
from playwright_guide.sidebar import install_sidebar, wait_for_user_message


@pytest.mark.parametrize(
    "reply, expected",
    [
        ("Find the Wind Degree box next to the Wind Speed box.", "wind_degree"),
        ("Click Show Fuel once Get Terrain/Fuel Data has loaded.", "show_fuel"),
        ("Use the map drawing row: click Set Fuel Brake.", "set_fuel_brake"),
        ("A fuel break stops the fire.", "set_fuel_brake"),
        ("Click Go to Project Location to return.", "go_project_location"),
        ("Nothing about controls here.", None),
    ],
)
def test_detect_step_picks_the_first_control_mentioned(reply, expected):
    assert detect_step(reply) == expected


def test_pick_highlight_trusts_the_server_list():
    reply = "Next to the Wind Speed box is Wind Degree."
    assert pick_highlight(["wind_degree"], reply) == "wind_degree"
    # Steps without a selector are skipped in favour of the next usable one.
    assert pick_highlight(["map_style", "close_project"], reply) == "close_project"
    # An empty list means "no control" — never second-guessed from the text.
    assert pick_highlight([], reply) is None
    assert pick_highlight(["show_results"], "Click Start Simulation Run first.") is None


def test_pick_highlight_falls_back_to_text_only_without_the_field():
    assert pick_highlight(None, "Next to the Wind Speed box is Wind Degree.") == "wind_speed"


# ---- browser tests -----------------------------------------------------------

# Each settings box sits in its own wrapper, which broke the old
# :nth-of-type selectors (they counted siblings, not page order).
FIXTURE_PAGE = """
<label for="sPL" style="color: rgb(1, 2, 3)">Set Project Location</label>
<label for="btnradio1">Set Line Ignition</label>
<label for="btnradio2">Set Fuel Brake</label>
<select id="cellResolution"><option>30</option></select>
<div class="group"><span>Simulation Duration (s):</span><input class="form-control" type="number" id="dur"></div>
<div class="group"><span>Wind Speed:</span><input class="form-control" type="number" id="ws"></div>
<div class="group"><span>Wind Degree:</span><input class="form-control" type="number" id="wd"></div>
<button>Close Project</button>
"""


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


@pytest.mark.parametrize(
    "key, element",
    [
        ("close_project", "button"),  # Playwright-only :has-text() selector
        ("simulation_duration", "#dur"),
        ("wind_speed", "#ws"),
        ("wind_degree", "#wd"),
        ("set_project_location", "label[for='sPL']"),
    ],
)
def test_highlight_on_outlines_the_right_control(page, key, element):
    page.set_content(FIXTURE_PAGE)

    assert highlight_on(page, STEP_SELECTORS[key], key)

    outlined = page.evaluate(
        "() => [...document.querySelectorAll('*')].filter(e => e.style.outline).map(e => e.outerHTML)"
    )
    assert outlined == [page.locator(element).evaluate("e => e.outerHTML")]


def test_highlight_off_restores_the_original_inline_style(page):
    page.set_content(FIXTURE_PAGE)
    selector = STEP_SELECTORS["set_project_location"]

    highlight_on(page, selector, "set_project_location")
    highlight_off(page)

    assert page.locator(selector).get_attribute("style") == "color: rgb(1, 2, 3)"


def test_highlight_off_clears_the_outline_even_after_a_re_render(page):
    # Regression (council review): highlight_off used to re-resolve the
    # selector; after a DOM change `nth=1` pointed at another input and the
    # old outline stayed on screen.
    page.set_content(FIXTURE_PAGE)
    highlight_on(page, STEP_SELECTORS["wind_speed"], "wind_speed")
    page.evaluate(
        """() => document.body.insertAdjacentHTML('afterbegin',
            '<input class="form-control" type="number" id="new">')"""
    )

    highlight_off(page)

    assert page.locator("#ws").evaluate("e => e.style.outline") == ""


def test_highlight_on_missing_control_returns_quickly(page):
    page.set_content("<p>no controls</p>")

    assert highlight_on(page, STEP_SELECTORS["wind_speed"], "wind_speed") is False


def test_every_selector_is_a_valid_playwright_selector(page):
    page.set_content(FIXTURE_PAGE)
    for key, selector in STEP_SELECTORS.items():
        page.locator(selector).count()  # raises on a malformed selector


def test_sidebar_is_re_injected_after_a_reload_and_round_trips_a_message(page):
    page.goto("data:text/html,<p>FireMapSim</p>")
    install_sidebar(page, 360, "welcome")

    page.reload()

    # Regression: the sidebar used to be injected once, so a reload lost it.
    assert page.evaluate("() => typeof window.__fsai_pending__") == "object"
    assert page.locator("#__fsai_sidebar__").count() == 1

    page.evaluate("() => window.__fsai_toggle__(true)")
    page.fill("#__fsai_input__", "How do I set wind speed?")
    page.press("#__fsai_input__", "Enter")

    assert wait_for_user_message(page) == "How do I set wind speed?"
    assert page.evaluate("() => window.__fsai_pending__") is None


def test_wait_ignores_an_undefined_pending_flag(page):
    # Regression: before the sidebar script runs (e.g. mid-reload) the flag is
    # undefined, which the old `!== null` wait accepted as a message at once.
    page.goto("data:text/html,<p>no sidebar yet</p>")
    page.evaluate("() => setTimeout(() => { window.__fsai_pending__ = 'hello'; }, 200)")

    assert wait_for_user_message(page) == "hello"


def test_sidebar_is_not_injected_into_iframes(page):
    page.goto("data:text/html,<p>top</p>")
    install_sidebar(page, 360, "welcome")
    # A real navigation, so the init script runs in the page and its frame.
    page.goto("data:text/html,<p>top</p><iframe srcdoc='<p>frame</p>'></iframe>")

    frame = page.frames[1]
    frame.wait_for_load_state()
    assert page.locator("#__fsai_sidebar__").count() == 1
    assert frame.locator("#__fsai_sidebar__").count() == 0


def test_sidebar_renders_replies_as_text_not_html(page):
    page.goto("data:text/html,<p>FireMapSim</p>")
    install_sidebar(page, 360, "welcome")

    page.evaluate("(t) => window.__fsai_append_agent__(t)", "<img src=x onerror=alert(1)>")

    assert page.locator("#__fsai_msg_area__ img").count() == 0
    assert "<img src=x" in page.locator("#__fsai_msg_area__").inner_text()
