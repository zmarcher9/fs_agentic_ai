"""
Maps agent replies to FireMapSim UI selectors and highlights them on the
live page — used by playwright/guide.py.
"""

from playwright.sync_api import Locator, Page

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
    "simulation_duration":  "input.form-control[type='number']:nth-of-type(1)",
    "wind_speed":           "input.form-control[type='number']:nth-of-type(2)",
    "wind_degree":          "input.form-control[type='number']:nth-of-type(3)",
    "start_simulation":     "label[for='startRun']",
    "reset_simulation":     "label[for='btnradio10']",
    "close_project":        "button:has-text('Close Project')",
    "load_sample":          "label[for='loadSample']",
    "save_project":         "label[for='saveProject']",
    "download_project":     "label[for='downloadProject']",
    "upload_project":       "label[for='uploadProject']",
    "map":                  ".map-layer canvas",
}

KEYWORD_MAP: list[tuple[str, str]] = [
    # Most specific UI control names first; ignition before generic "duration".
    ("set line ignition",    "set_line_ignition"),
    ("set point ignition",   "set_point_ignition"),
    ("line ignition",        "set_line_ignition"),
    ("point ignition",       "set_point_ignition"),
    ("set fuel brake",       "set_fuel_brake"),
    ("set project location", "set_project_location"),
    ("cell resolution",      "cell_resolution"),
    ("cell space",           "cell_dimension"),
    ("get terrain",          "get_terrain_fuel"),
    ("wind speed",           "wind_speed"),
    ("wind degree",          "wind_degree"),
    ("wind direction",       "wind_degree"),
    ("simulation duration",  "simulation_duration"),
    ("start simulation",     "start_simulation"),
    ("reset simulation",     "reset_simulation"),
    ("go to project",        "go_project_location"),
    ("fuel brake",           "set_fuel_brake"),
    ("show fuel",            "show_fuel"),
    ("show slope",           "show_slope"),
    ("show aspect",          "show_aspect"),
    ("close project",        "close_project"),
    ("load sample",          "load_sample"),
    ("save project",         "save_project"),
    ("download project",     "download_project"),
    ("upload project",       "upload_project"),
    ("the map",              "map"),
    ("mapbox",               "map"),
]


def detect_step(reply: str) -> str | None:
    """Return highlight key by scanning the reply for known UI control phrases."""
    lower = reply.lower()
    for phrase, key in KEYWORD_MAP:
        if phrase in lower:
            return key
    return None


def highlight_on(page: Page, selector: str, label: str) -> None:
    try:
        locator: Locator = page.locator(selector).first
        locator.scroll_into_view_if_needed(timeout=5000)
        page.evaluate(
            """([sel, css]) => {
                const el = document.querySelector(sel);
                if (el) {
                    el._originalOutline = el.style.outline || '';
                    el._originalBg      = el.style.backgroundColor || '';
                    el.style.cssText += css;
                }
            }""",
            [selector, HIGHLIGHT_CSS],
        )
        print(f"  -> Highlighted: {label}  [{selector}]")
    except Exception as exc:
        print(f"  !  Could not highlight '{selector}': {exc}")


def highlight_off(page: Page, selector: str) -> None:
    try:
        page.evaluate(
            """([sel]) => {
                const el = document.querySelector(sel);
                if (el) {
                    el.style.outline         = el._originalOutline || '';
                    el.style.backgroundColor = el._originalBg || '';
                }
            }""",
            [selector],
        )
    except Exception:
        pass
