"""
playwright/guide.py

FireMapSim UI walkthrough guide.
Launches or attaches to https://firesim.cs.gsu.edu/,
then highlights UI fields as the agent narrates each setup step.

Usage:
    python playwright/guide.py

The script:
  1. Opens FireMapSim in a visible browser window.
  2. Sends each demo message to the local firesim-ai API (localhost:8000/chat).
  3. Parses the agent reply to detect which UI element to highlight.
  4. Scrolls to + visually highlights that element on the live page.
  5. Pauses so the user can read the narration before moving on.

Requires:
    pip install playwright requests
    playwright install chromium
"""

import time
import json
import re
import requests
from playwright.sync_api import sync_playwright, Page, Locator

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FIRESIM_URL = "https://firesim.cs.gsu.edu/"
API_URL     = "http://localhost:8000/chat"
THREAD_ID   = "guide-demo-001"

# How long (seconds) to hold the highlight before moving to the next step.
PAUSE_AFTER_HIGHLIGHT = 4

# Highlight style injected via JS.
HIGHLIGHT_CSS = """
  outline: 4px solid #ff6600 !important;
  outline-offset: 3px !important;
  background-color: rgba(255, 102, 0, 0.12) !important;
  transition: all 0.3s ease;
"""

# ---------------------------------------------------------------------------
# Selector map
# Maps agent-detected step keywords → CSS selectors in FireMapSim's DOM.
# ---------------------------------------------------------------------------

STEP_SELECTORS: dict[str, str] = {
    # Grid / resolution controls (top toolbar)
    "cell_resolution":      "select#cellResolution",
    "cell_dimension":       "select#cellSpaceDimension",
    "selected_area":        "span#selectedSquareArea",

    # Location buttons (radio-button-style)
    "set_project_location": "label[for='sPL']",
    "go_project_location":  "label[for='gPL']",

    # Ignition mode buttons
    "set_line_ignition":    "label[for='btnradio1']",
    "set_point_ignition":   "label[for='btnradio1-1']",
    "set_fuel_brake":       "label[for='btnradio2']",

    # Terrain data
    "get_terrain_fuel":     "label[for='getFuel']",
    "show_fuel":            "label[for='drawFuel']",
    "show_slope":           "label[for='drawSlope']",
    "show_aspect":          "label[for='drawAspect']",

    # Simulation parameters (the input-group row)
    "simulation_duration":  "input.form-control[type='number']:nth-of-type(1)",
    "wind_speed":           "input.form-control[type='number']:nth-of-type(2)",
    "wind_degree":          "input.form-control[type='number']:nth-of-type(3)",

    # Simulation control
    "start_simulation":     "label[for='startRun']",
    "reset_simulation":     "label[for='btnradio10']",
    "close_project":        "button:has-text('Close Project')",

    # Project persistence
    "load_sample":          "label[for='loadSample']",
    "save_project":         "label[for='saveProject']",
    "download_project":     "label[for='downloadProject']",
    "upload_project":       "label[for='uploadProject']",

    # Map canvas itself
    "map":                  ".map-layer canvas",
}


# ---------------------------------------------------------------------------
# Keyword → step key mapping
# We scan the agent reply for these phrases and map them to STEP_SELECTORS.
# ---------------------------------------------------------------------------

KEYWORD_MAP: list[tuple[str, str]] = [
    # Check for specific field names first (more specific → earlier in list)
    ("simulation duration",  "simulation_duration"),
    ("wind speed",           "wind_speed"),
    ("wind degree",          "wind_degree"),
    ("wind direction",       "wind_degree"),
    ("cell resolution",      "cell_resolution"),
    ("cell space",           "cell_dimension"),
    ("set project location", "set_project_location"),
    ("go to project",        "go_project_location"),
    ("set line ignition",    "set_line_ignition"),
    ("set point ignition",   "set_point_ignition"),
    ("set fuel brake",       "set_fuel_brake"),
    ("fuel brake",           "set_fuel_brake"),
    ("get terrain",          "get_terrain_fuel"),
    ("show fuel",            "show_fuel"),
    ("show slope",           "show_slope"),
    ("show aspect",          "show_aspect"),
    ("start simulation",     "start_simulation"),
    ("reset simulation",     "reset_simulation"),
    ("close project",        "close_project"),
    ("load sample",          "load_sample"),
    ("save project",         "save_project"),
    ("download project",     "download_project"),
    ("upload project",       "upload_project"),
    ("the map",              "map"),
    ("mapbox",               "map"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def chat(message: str) -> str:
    """Send a message to the firesim-ai agent and return the reply."""
    resp = requests.post(API_URL, json={"message": message, "thread_id": THREAD_ID}, timeout=120)
    resp.raise_for_status()
    return resp.json()["reply"]


def detect_step(reply: str) -> str | None:
    """
    Scan the agent reply for known keywords and return the matching step key,
    or None if nothing is recognised.
    """
    lower = reply.lower()
    for phrase, key in KEYWORD_MAP:
        if phrase in lower:
            return key
    return None


def highlight(page: Page, selector: str, label: str) -> None:
    """
    Scroll the element into view and apply an orange outline for PAUSE seconds.
    Removes the highlight afterward so the next step starts clean.
    """
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
        print(f"  → Highlighted: {label}  [{selector}]")
        time.sleep(PAUSE_AFTER_HIGHLIGHT)
        # Remove highlight
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
    except Exception as exc:
        print(f"  ⚠  Could not highlight '{selector}': {exc}")


def narrate(reply: str) -> None:
    """Print the agent reply to the terminal with a clear separator."""
    print("\n" + "─" * 60)
    print(reply)
    print("─" * 60 + "\n")


# ---------------------------------------------------------------------------
# Demo conversation script  (Canton, GA prescribed burn walkthrough)
# ---------------------------------------------------------------------------

DEMO_SCRIPT = [
    "I want to set up a prescribed burn simulation near Canton, GA.",
    "What cell resolution and cell space dimension should I use?",
    "How do I set the project location on the map?",
    "Where do I enter wind speed and wind direction?",
    "What simulation duration should I use for a prescribed burn?",
    "How do I get the terrain and fuel data for this area?",
    "Walk me through setting an ignition line.",
    "How do I start the simulation once everything is configured?",
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    with sync_playwright() as pw:
        # Launch a visible Chromium browser.
        browser = pw.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(viewport={"width": 1400, "height": 900})
        page    = context.new_page()

        print(f"Opening FireMapSim at {FIRESIM_URL} …")
        page.goto(FIRESIM_URL, wait_until="networkidle", timeout=60000)
        print("Page loaded.  Starting guided walkthrough.\n")

        # Give the Vue app a moment to finish rendering.
        time.sleep(3)

        for turn, user_msg in enumerate(DEMO_SCRIPT, start=1):
            print(f"\n[Turn {turn}/{len(DEMO_SCRIPT)}]  User: {user_msg}")

            # 1. Send message to agent
            try:
                reply = chat(user_msg)
            except Exception as exc:
                print(f"  ✗ API error: {exc}")
                continue

            # 2. Print agent reply
            narrate(reply)

            # 3. Detect which UI element to highlight
            step_key = detect_step(reply)
            if step_key and step_key in STEP_SELECTORS:
                highlight(page, STEP_SELECTORS[step_key], step_key)
            else:
                print("  (no specific UI element detected — pausing briefly)")
                time.sleep(2)

        print("\n✓ Guided walkthrough complete.")
        print("  The browser will stay open for 10 seconds so you can inspect the page.")
        time.sleep(10)
        browser.close()


if __name__ == "__main__":
    main()
