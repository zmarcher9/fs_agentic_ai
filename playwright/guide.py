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
  5. Shows a caption box on the page with the step's instruction and
     a "Next step" / "Quit" button.
  6. Waits for the user to click a button on the page before continuing.
     (No need to switch back to the terminal.)
 
Requires:
    pip install playwright requests
    playwright install chromium
"""

import os
import time
import textwrap
import requests
from playwright.sync_api import sync_playwright, Page, Locator

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FIRESIM_URL = "https://firesim.cs.gsu.edu/"
API_URL     = "http://localhost:8000/chat"

# Shared with demo/run_demo.py via the FIRESIM_THREAD_ID env var, so both
# scripts talk to the same agent conversation. If run_demo.py was run first,
# set this to the same value (it prints the thread ID it used) e.g.:
#
#   export FIRESIM_THREAD_ID=canton-demo-20260615-130800   (bash)
#   $env:FIRESIM_THREAD_ID = "canton-demo-20260615-130800" (PowerShell)
#
# If unset, falls back to a fixed default thread shared by both scripts.
THREAD_ID = os.environ.get("FIRESIM_THREAD_ID", "canton-demo-default")

# Max characters of the agent reply to show in the on-page caption.
CAPTION_MAX_CHARS = 280

# Highlight style injected via JS.
HIGHLIGHT_CSS = """
  outline: 4px solid #ff6600 !important;
  outline-offset: 3px !important;
  background-color: rgba(255, 102, 0, 0.12) !important;
  transition: all 0.3s ease;
"""

# CSS for the floating caption box. !important on everything so the host
# page's stylesheet (which may use very broad/aggressive selectors) can't
# hide, clip, or reposition it.
CAPTION_CSS = """
  all: initial !important;
  position: fixed !important;
  bottom: 24px !important;
  left: 24px !important;
  right: 24px !important;
  max-width: 640px !important;
  width: auto !important;
  z-index: 2147483647 !important;
  display: block !important;
  visibility: visible !important;
  opacity: 1 !important;
  background: #1e1e1e !important;
  color: #fff !important;
  font-family: -apple-system, Segoe UI, Roboto, sans-serif !important;
  font-size: 15px !important;
  line-height: 1.4 !important;
  padding: 14px 18px !important;
  border-radius: 10px !important;
  border-left: 5px solid #ff6600 !important;
  box-shadow: 0 6px 20px rgba(0,0,0,0.35) !important;
  box-sizing: border-box !important;
"""

CAPTION_HINT_CSS = """
  margin-top: 8px !important;
  font-size: 12px !important;
  color: #aaa !important;
  display: block !important;
"""

CAPTION_BUTTON_ROW_CSS = """
  margin-top: 12px !important;
  display: flex !important;
  gap: 10px !important;
  justify-content: flex-end !important;
"""

NEXT_BUTTON_CSS = """
  all: initial !important;
  background: #ff6600 !important;
  color: #1e1e1e !important;
  border: none !important;
  font-weight: 600 !important;
  font-family: -apple-system, Segoe UI, Roboto, sans-serif !important;
  font-size: 14px !important;
  padding: 8px 18px !important;
  border-radius: 6px !important;
  cursor: pointer !important;
  display: inline-block !important;
"""

QUIT_BUTTON_CSS = """
  all: initial !important;
  background: transparent !important;
  color: #ccc !important;
  border: 1px solid #555 !important;
  font-family: -apple-system, Segoe UI, Roboto, sans-serif !important;
  font-size: 14px !important;
  padding: 8px 14px !important;
  border-radius: 6px !important;
  cursor: pointer !important;
  display: inline-block !important;
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


def shorten(text: str, max_chars: int) -> str:
    """Collapse whitespace and trim long agent replies for the on-page caption."""
    flat = " ".join(text.split())
    if len(flat) <= max_chars:
        return flat
    return flat[: max_chars - 1].rsplit(" ", 1)[0] + "…"


def show_caption(page: Page, turn: int, total: int, message: str, is_last: bool) -> None:
    """
    Render a single floating caption box on the page with the current
    step's instruction, plus "Next step" / "Quit" buttons. Replaces any
    caption from the previous step. Clicking a button sets
    window.__guide_action__ to "next" or "quit", which the Python side
    polls for via wait_for_page_action().
    """
    safe_message = message.replace("\\", "\\\\").replace("`", "\\`")
    next_label = "Finish" if is_last else "Next step"

    page.evaluate(
        """([msg, turn, total, nextLabel, captionCss, btnRowCss, nextCss, quitCss]) => {
            try {
                window.__guide_action__ = null;

                let box = document.getElementById('__guide_caption__');
                if (!box) {
                    box = document.createElement('div');
                    box.id = '__guide_caption__';
                    (document.body || document.documentElement).appendChild(box);
                }
                box.setAttribute('style', captionCss);
                box.innerHTML =
                    '<div style="all:initial !important; display:block !important; font-weight:600 !important; margin-bottom:4px !important; color:#fff !important; font-family:inherit !important; font-size:15px !important;">Step ' + turn + ' / ' + total + '</div>' +
                    '<div style="all:initial !important; display:block !important; color:#fff !important; font-family:inherit !important; font-size:15px !important; line-height:1.4 !important;">' + msg + '</div>' +
                    '<div style="' + btnRowCss + '">' +
                        '<button id="__guide_quit__" style="' + quitCss + '">Quit</button>' +
                        '<button id="__guide_next__" style="' + nextCss + '">' + nextLabel + '</button>' +
                    '</div>';

                document.getElementById('__guide_next__').onclick = () => {
                    window.__guide_action__ = 'next';
                };
                document.getElementById('__guide_quit__').onclick = () => {
                    window.__guide_action__ = 'quit';
                };
            } catch (e) {
                console.error('guide caption error:', e);
                // Make sure we never hang forever if rendering fails.
                window.__guide_action__ = 'next';
            }
        }""",
        [safe_message, turn, total, next_label, CAPTION_CSS, CAPTION_BUTTON_ROW_CSS, NEXT_BUTTON_CSS, QUIT_BUTTON_CSS],
    )


def remove_caption(page: Page) -> None:
    """Remove the floating caption box from the page, if present."""
    page.evaluate(
        """() => {
            const box = document.getElementById('__guide_caption__');
            if (box) box.remove();
        }"""
    )


def highlight_on(page: Page, selector: str, label: str) -> None:
    """Scroll the element into view and apply an orange outline."""
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
    """Remove the highlight applied by highlight_on, if any."""
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


def wait_for_page_action(page: Page) -> str:
    """
    Block until the user clicks "Next step"/"Finish" or "Quit" in the
    on-page caption. Returns "next" or "quit".
    """
    page.wait_for_function(
        "() => window.__guide_action__ === 'next' || window.__guide_action__ === 'quit'",
        timeout=0,  # no timeout — wait as long as the user needs
    )
    return page.evaluate("() => window.__guide_action__")


def narrate(reply: str) -> None:
    """Print the full agent reply to the terminal with a clear separator."""
    print("\n" + "-" * 60)
    print(textwrap.fill(reply, width=78))
    print("-" * 60 + "\n")


def show_end_screen(page: Page, completed: bool) -> None:
    """
    Replace the caption with a final message and a single 'Close browser'
    button. Sets window.__guide_action__ = 'close' when clicked.
    """
    if completed:
        heading = "Walkthrough complete"
        body = "You've gone through every step. Feel free to keep exploring FireMapSim, or close this window when you're done."
    else:
        heading = "Walkthrough stopped"
        body = "You can keep exploring FireMapSim, or close this window when you're done."

    page.evaluate(
        """([heading, body, captionCss, btnRowCss, nextCss]) => {
            try {
                window.__guide_action__ = null;

                let box = document.getElementById('__guide_caption__');
                if (!box) {
                    box = document.createElement('div');
                    box.id = '__guide_caption__';
                    (document.body || document.documentElement).appendChild(box);
                }
                box.setAttribute('style', captionCss);
                box.innerHTML =
                    '<div style="all:initial !important; display:block !important; font-weight:600 !important; margin-bottom:4px !important; color:#fff !important; font-family:inherit !important; font-size:15px !important;">' + heading + '</div>' +
                    '<div style="all:initial !important; display:block !important; color:#fff !important; font-family:inherit !important; font-size:15px !important; line-height:1.4 !important;">' + body + '</div>' +
                    '<div style="' + btnRowCss + '">' +
                        '<button id="__guide_close__" style="' + nextCss + '">Close browser</button>' +
                    '</div>';

                document.getElementById('__guide_close__').onclick = () => {
                    window.__guide_action__ = 'close';
                };
            } catch (e) {
                console.error('guide end screen error:', e);
                window.__guide_action__ = 'close';
            }
        }""",
        [heading, body, CAPTION_CSS, CAPTION_BUTTON_ROW_CSS, NEXT_BUTTON_CSS],
    )


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

        print(f"Opening FireMapSim at {FIRESIM_URL} ...")
        page.goto(FIRESIM_URL, wait_until="networkidle", timeout=60000)
        print("Page loaded.  Starting guided walkthrough.\n")
        print("Use the 'Next step' / 'Quit' buttons in the on-page caption box")
        print("to control pacing — no need to switch back to this terminal.\n")

        # Give the Vue app a moment to finish rendering.
        time.sleep(3)

        total = len(DEMO_SCRIPT)
        active_selector: str | None = None
        completed = False

        for turn, user_msg in enumerate(DEMO_SCRIPT, start=1):
            print(f"\n[Turn {turn}/{total}]  User: {user_msg}")

            # 1. Send message to agent
            try:
                reply = chat(user_msg)
            except Exception as exc:
                print(f"  x API error: {exc}")
                reply = f"(Could not reach the agent for this step: {exc})"

            # 2. Print full agent reply in the terminal (log only)
            narrate(reply)

            # 3. Detect which UI element to highlight and apply it
            step_key = detect_step(reply)
            if step_key and step_key in STEP_SELECTORS:
                selector = STEP_SELECTORS[step_key]
                highlight_on(page, selector, step_key)
                active_selector = selector
            else:
                print("  (no specific UI element detected for this step)")
                active_selector = None

            # 4. Show the caption with Next/Quit buttons
            caption_text = shorten(reply, CAPTION_MAX_CHARS)
            is_last = turn == total

            try:
                show_caption(page, turn, total, caption_text, is_last)
                # 5. Wait for the user to click Next/Finish or Quit on the page
                action = wait_for_page_action(page)
            except Exception as exc:
                print(f"  !  Caption/button error, continuing automatically: {exc}")
                action = "next"

            # 6. Clean up this step's highlight before moving on
            if active_selector:
                highlight_off(page, active_selector)

            if action == "quit":
                print("\nWalkthrough stopped early by user.")
                break
        else:
            completed = True
            print("\nGuided walkthrough complete.")

        # Final screen: stays open until the user clicks "Close browser"
        try:
            show_end_screen(page, completed)
            wait_for_page_action_close(page)
        except Exception as exc:
            print(f"  !  End screen error: {exc}")
        browser.close()


def wait_for_page_action_close(page: Page) -> None:
    """Block until the user clicks 'Close browser' on the end screen."""
    page.wait_for_function(
        "() => window.__guide_action__ === 'close'",
        timeout=0,
    )


if __name__ == "__main__":
    main()