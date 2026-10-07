"""
Maps agent replies to FireMapSim UI selectors and highlights them on the
live page — used by playwright/guide.py.

Selectors are Playwright selectors (CSS plus Playwright extensions such as
`>> nth=` and `:has-text()`), always resolved through page.locator — never
document.querySelector, which rejects the extensions.
"""

from playwright.sync_api import Page

HIGHLIGHT_CSS = """
  outline: 4px solid #ff6600 !important;
  outline-offset: 3px !important;
  background-color: rgba(255, 102, 0, 0.12) !important;
  transition: all 0.3s ease;
"""

STEP_SELECTORS: dict[str, str] = {
    "cell_resolution":      "select#cellResolution",
    "cell_dimension":       "select#cellSpaceDimension",
    "selected_area":        "span#selectedSquareArea",
    "set_project_location": "label[for='sPL']",
    "go_project_location":  "label[for='gPL']",
    "set_line_ignition":    "label[for='btnradio1']",
    "set_point_ignition":   "label[for='btnradio1-1']",
    "set_fuel_brake":       "label[for='btnradio2']",
    "get_terrain_fuel":     "label[for='getFuel']",
    "show_fuel":            "label[for='drawFuel']",
    "show_slope":           "label[for='drawSlope']",
    "show_aspect":          "label[for='drawAspect']",
    # The three settings boxes in page order (Duration, Wind Speed, Wind
    # Degree). `nth=` counts matches across the whole page; CSS
    # :nth-of-type counted siblings and broke when each box has its own
    # wrapper. Not yet checked against the live DOM.
    "simulation_duration":  "input.form-control[type='number'] >> nth=0",
    "wind_speed":           "input.form-control[type='number'] >> nth=1",
    "wind_degree":          "input.form-control[type='number'] >> nth=2",
    "start_simulation":     "label[for='startRun']",
    "reset_simulation":     "label[for='btnradio10']",
    "close_project":        "button:has-text('Close Project')",
    "load_sample":          "label[for='loadSample']",
    "save_project":         "label[for='saveProject']",
    "download_project":     "label[for='downloadProject']",
    "upload_project":       "label[for='uploadProject']",
}

# Phrase → step key. detect_step picks the phrase that appears EARLIEST in
# the reply (longest phrase on ties), so list order doesn't matter.
KEYWORD_MAP: list[tuple[str, str]] = [
    ("set line ignition",      "set_line_ignition"),
    ("line ignition",          "set_line_ignition"),
    ("set point ignition",     "set_point_ignition"),
    ("point ignition",         "set_point_ignition"),
    ("set fuel brake",         "set_fuel_brake"),
    ("fuel brake",             "set_fuel_brake"),
    ("fuel break",             "set_fuel_brake"),
    ("set project location",   "set_project_location"),
    ("go to project location", "go_project_location"),
    ("selected region",        "selected_area"),
    ("cell resolution",        "cell_resolution"),
    ("cell space",             "cell_dimension"),
    ("get terrain",            "get_terrain_fuel"),
    ("show fuel",              "show_fuel"),
    ("hide fuel",              "show_fuel"),
    ("show slope",             "show_slope"),
    ("show aspect",            "show_aspect"),
    ("wind speed",             "wind_speed"),
    ("wind degree",            "wind_degree"),
    ("wind direction",         "wind_degree"),
    ("simulation duration",    "simulation_duration"),
    ("start simulation",       "start_simulation"),
    ("reset simulation",       "reset_simulation"),
    ("close project",          "close_project"),
    ("load sample",            "load_sample"),
    ("save project",           "save_project"),
    ("download project",       "download_project"),
    ("upload project",         "upload_project"),
]


def detect_step(reply: str) -> str | None:
    """Return the highlight key for the control the reply mentions first."""
    lower = reply.lower()
    best: tuple[int, int, str] | None = None  # (position, -len(phrase), key)
    for phrase, key in KEYWORD_MAP:
        position = lower.find(phrase)
        if position == -1:
            continue
        candidate = (position, -len(phrase), key)
        if best is None or candidate < best:
            best = candidate
    return best[2] if best else None


def pick_highlight(highlight: list[str] | None, reply: str) -> str | None:
    """Choose the control to outline.

    `highlight` is /chat's list of step keys the answer is about. It is the
    source of truth: the first key we have a selector for wins, and an empty
    list (or one with no selectable key) means highlight nothing. Only when
    the field is missing entirely (an older server) do we guess from the
    reply text.
    """
    if highlight is None:
        return detect_step(reply)
    for step in highlight:
        if step in STEP_SELECTORS:
            return step
    return None


def highlight_on(page: Page, selector: str, label: str) -> bool:
    """Outline the control. Returns False (without waiting) if it isn't on the page."""
    try:
        locator = page.locator(selector).first
        if locator.count() == 0:
            print(f"  !  '{label}' isn't on the page right now  [{selector}]")
            return False
        locator.scroll_into_view_if_needed(timeout=2000)
        locator.evaluate(
            """(el, css) => {
                if (el.dataset.fsaiOrigStyle === undefined) {
                    el.dataset.fsaiOrigStyle = el.getAttribute('style') || '';
                }
                el.style.cssText += css;
            }""",
            HIGHLIGHT_CSS,
        )
        print(f"  -> Highlighted: {label}  [{selector}]")
        return True
    except Exception as exc:
        print(f"  !  Could not highlight '{selector}': {exc}")
        return False


def highlight_off(page: Page) -> None:
    """Restore every highlighted control's original inline style exactly.

    Finds them by the marker highlight_on leaves, not by re-resolving a
    selector: if the page re-rendered, the selector may now point at a
    different element and the old outline would be left behind.
    """
    try:
        page.evaluate(
            """() => {
                for (const el of document.querySelectorAll('[data-fsai-orig-style]')) {
                    el.setAttribute('style', el.dataset.fsaiOrigStyle);
                    delete el.dataset.fsaiOrigStyle;
                }
            }"""
        )
    except Exception:
        pass
