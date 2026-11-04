"""Tests for the embeddable FireMapSim widget (widget/firesim-helper.js).

The fixture page and the API are served from one fake origin through
page.route, so the widget runs exactly as it would with its one-line embed:
it loads from the API, defaults its API URL to that origin, mints a session
and posts to /chat.
"""

import json

import pytest

from api.main import _widget_source
from app.ui_selectors import STEP_SELECTORS
from tests.test_highlighting import FIXTURE_PAGE

ORIGIN = "http://firesim.test"
EMBED = '<script src="/widget/firesim-helper.js" defer></script>'


def _json(route, status, body):
    route.fulfill(status=status, content_type="application/json", body=json.dumps(body))


@pytest.fixture
def api(page):
    """Serve the page, the widget, and a scripted API. Returns the call log."""
    state = {"replies": [], "chats": [], "sessions": 0, "expire_next": False}

    def handle(route):
        request = route.request
        path = request.url[len(ORIGIN):]
        if path == "/":
            route.fulfill(content_type="text/html", body=FIXTURE_PAGE + EMBED)
        elif path == "/widget/firesim-helper.js":
            route.fulfill(content_type="application/javascript", body=_widget_source())
        elif path == "/api/session":
            state["sessions"] += 1
            _json(route, 200, {"session_id": f"sid-{state['sessions']}"})
        elif path == "/chat":
            sid = request.headers.get("x-session-id")
            if state["expire_next"]:
                state["expire_next"] = False
                _json(route, 401, {"detail": "Missing or invalid X-Session-Id"})
                return
            state["chats"].append((sid, request.post_data_json["message"]))
            status, body = state["replies"].pop(0)
            _json(route, status, body)
        else:
            route.fulfill(status=404, body="")

    page.route(f"{ORIGIN}/**", handle)
    return state


def _open(page):
    page.goto(f"{ORIGIN}/")
    page.wait_for_function("() => window.__fsaiHelper && window.__fsaiHelper.open")
    page.locator("#fsai-helper .launcher").click()


def _ask(page, text, bubbles_before):
    page.locator("#fsai-helper input").fill(text)
    page.locator("#fsai-helper input").press("Enter")
    # user bubble + reply bubble
    page.wait_for_function(
        "n => document.getElementById('fsai-helper').shadowRoot"
        ".querySelectorAll('.row:not(.typing)').length >= n",
        arg=bubbles_before + 2,
    )


def _bubbles(page):
    return page.locator("#fsai-helper .row:not(.typing) .bubble").all_inner_texts()


def _outlined(page):
    return page.evaluate(
        "() => [...document.querySelectorAll('[data-fsai-orig-style]')].map(e => e.id || e.outerHTML)"
    )


def test_served_widget_has_the_selector_map_filled_in():
    source = _widget_source()

    assert "__FSAI_SELECTORS__" not in source
    assert json.dumps(STEP_SELECTORS) in source


def test_one_line_embed_adds_a_closed_floating_helper(page, api):
    page.goto(f"{ORIGIN}/")
    page.wait_for_function("() => window.__fsaiHelper && window.__fsaiHelper.open")
    width_before = page.evaluate("() => document.body.clientWidth")

    assert page.locator("#fsai-helper .panel").is_hidden()
    page.locator("#fsai-helper .launcher").click()

    assert page.locator("#fsai-helper .panel").is_visible()
    assert page.evaluate("() => document.body.clientWidth") == width_before
    assert api["sessions"] == 0  # no session until the first question


def test_a_question_round_trips_and_highlights_the_control(page, api):
    api["replies"] = [
        (200, {"reply": "Wind Degree is next to Wind Speed.", "session_id": "sid-1",
               "highlight": ["wind_degree", "wind_speed"]}),
        (200, {"reply": "Hello!", "session_id": "sid-1", "highlight": []}),
    ]
    _open(page)

    _ask(page, "Where is wind degree?", 1)

    assert api["chats"] == [("sid-1", "Where is wind degree?")]
    assert _bubbles(page)[-1] == "Wind Degree is next to Wind Speed."
    assert _outlined(page) == ["wd"]  # first key only

    _ask(page, "hi", 3)

    # Same session reused; an empty list clears the old outline.
    assert api["chats"][-1] == ("sid-1", "hi")
    assert _outlined(page) == []


@pytest.mark.parametrize(
    "key, element",
    [
        # :has-text() resolved by the widget itself. "body > button": Playwright
        # also sees the widget's own buttons inside its shadow root.
        ("close_project", "body > button"),
        ("simulation_duration", "#dur"),  # >> nth=
        ("wind_speed", "#ws"),
        ("wind_degree", "#wd"),
        ("set_project_location", "label[for='sPL']"),
    ],
)
def test_widget_resolves_selectors_like_playwright(page, api, key, element):
    page.goto(f"{ORIGIN}/")
    page.wait_for_function("() => window.__fsaiHelper && window.__fsaiHelper.highlight")

    page.evaluate("k => window.__fsaiHelper.highlight([k])", key)

    # Exactly one element outlined, and it is the one Playwright resolves.
    assert page.locator("[data-fsai-orig-style]").count() == 1
    assert page.locator(STEP_SELECTORS[key]).first.evaluate("e => e.hasAttribute('data-fsai-orig-style')")
    assert page.locator(element).evaluate("e => e.style.outline") != ""


def test_clear_restores_the_original_inline_style(page, api):
    page.goto(f"{ORIGIN}/")
    page.wait_for_function("() => window.__fsaiHelper && window.__fsaiHelper.highlight")

    page.evaluate("() => window.__fsaiHelper.highlight(['set_project_location'])")
    page.evaluate("() => window.__fsaiHelper.clearHighlight()")

    assert page.locator("label[for='sPL']").get_attribute("style") == "color: rgb(1, 2, 3)"


def test_an_expired_session_is_re_minted_and_the_question_retried(page, api):
    api["replies"] = [(200, {"reply": "ok", "session_id": "sid-2", "highlight": []})]
    api["expire_next"] = True
    _open(page)

    _ask(page, "still there?", 1)

    assert api["sessions"] == 2
    assert api["chats"] == [("sid-2", "still there?")]
    assert _bubbles(page)[-1] == "ok"


def test_rate_limit_detail_is_shown_and_other_errors_are_generic(page, api):
    api["replies"] = [
        (429, {"detail": "Chat limit reached. Try again in 30 seconds."}),
        (500, {"detail": "internal stack trace"}),
    ]
    _open(page)

    _ask(page, "one", 1)
    assert _bubbles(page)[-1] == "Chat limit reached. Try again in 30 seconds."

    _ask(page, "two", 3)
    assert "stack trace" not in _bubbles(page)[-1]
    assert page.locator("#fsai-helper .row.error").count() == 2


def test_replies_render_as_text_not_html(page, api):
    api["replies"] = [(200, {"reply": "<img src=x onerror=alert(1)>", "session_id": "sid-1", "highlight": []})]
    _open(page)

    _ask(page, "xss?", 1)

    assert page.locator("#fsai-helper img").count() == 0
    assert _bubbles(page)[-1] == "<img src=x onerror=alert(1)>"


def test_transcript_and_session_survive_a_reload(page, api):
    api["replies"] = [
        (200, {"reply": "first answer", "session_id": "sid-1", "highlight": []}),
        (200, {"reply": "second answer", "session_id": "sid-1", "highlight": []}),
    ]
    _open(page)
    _ask(page, "first", 1)

    page.reload()
    _open(page)

    assert _bubbles(page)[-2:] == ["first", "first answer"]
    _ask(page, "second", 3)
    assert api["sessions"] == 1
    assert api["chats"][-1] == ("sid-1", "second")


def test_loading_the_script_twice_mounts_one_helper(page, api):
    page.goto(f"{ORIGIN}/")
    page.wait_for_function("() => window.__fsaiHelper && window.__fsaiHelper.open")

    page.add_script_tag(url=f"{ORIGIN}/widget/firesim-helper.js")

    assert page.locator("#fsai-helper").count() == 1


def test_typing_does_not_trigger_page_keyboard_shortcuts(page, api):
    _open(page)
    page.evaluate("() => { window.__keys = 0; document.addEventListener('keydown', () => window.__keys++); }")

    page.locator("#fsai-helper input").type("wind")

    assert page.evaluate("() => window.__keys") == 0
