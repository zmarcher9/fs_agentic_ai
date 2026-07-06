"""
playwright/guide.py

FireMapSim UI walkthrough guide.
Launches or attaches to https://firesim.cs.gsu.edu/,
then highlights UI fields as the agent narrates each setup step.

Usage:
    python playwright/guide.py

The script:
  1. Opens FireMapSim in a visible browser window.
  2. Injects a floating chat overlay so the agent is visible on-screen.
  3. Pans the map to the project location via Mapbox GL (Vue FireMap component).
  4. Sends each demo message to the local firesim-ai API (localhost:8000/chat).
  5. Parses the agent reply to detect which UI element to highlight.
  6. Scrolls to + visually highlights that element on the live page.
  7. Shows agent responses in the floating overlay (no raw JSON ever shown).
  8. Waits for the user to click "Next step" / "Quit" before continuing.

Requires:
    pip install playwright requests
    playwright install chromium
"""

import os
import re
import time
import textwrap
import requests
from playwright.sync_api import sync_playwright, Page, Locator

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FIRESIM_BASE = "https://firesim.cs.gsu.edu/home"
API_URL      = "http://localhost:8000/chat"

THREAD_ID = os.environ.get("FIRESIM_THREAD_ID", "canton-demo-default")

# Canton, GA prescribed burn center coordinates
PROJECT_LAT = 34.2367621
PROJECT_LNG = -84.4907621
PROJECT_ZOOM = 13  # zoom level — 13 gives a good neighbourhood view

# Max characters shown in the overlay per agent response.
OVERLAY_MAX_CHARS = 400

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

HIGHLIGHT_CSS = """
  outline: 4px solid #ff6600 !important;
  outline-offset: 3px !important;
  background-color: rgba(255, 102, 0, 0.12) !important;
  transition: all 0.3s ease;
"""

# ---------------------------------------------------------------------------
# Selector map
# ---------------------------------------------------------------------------

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
# Map panning via Mapbox GL (FireMapSim Vue component)
# ---------------------------------------------------------------------------

def firesim_url(lat: float, lng: float, zoom: int) -> str:
    """Open the sim UI directly; query params seed the initial map center."""
    return f"{FIRESIM_BASE}?lat={lat}&lng={lng}&zoom={zoom}"


PAN_MAP_JS = """
([lat, lng, zoom]) => {
    function findFireMap(vm) {
        if (!vm) return null;
        if (vm.$options && vm.$options.name === 'FireMap' && vm.map) return vm;
        const kids = vm.$children || [];
        for (let i = 0; i < kids.length; i++) {
            const found = findFireMap(kids[i]);
            if (found) return found;
        }
        return null;
    }

    function findMapboxOnDom() {
        const containers = document.querySelectorAll('.mapboxgl-map');
        for (const el of containers) {
            const keys = Object.getOwnPropertyNames(el);
            for (let i = 0; i < keys.length; i++) {
                const candidate = el[keys[i]];
                if (candidate && typeof candidate.jumpTo === 'function') {
                    return candidate;
                }
            }
        }
        return null;
    }

    const root = document.querySelector('#app');
    const fireMap = findFireMap(root && root.__vue__);
    let map = fireMap && fireMap.map ? fireMap.map : findMapboxOnDom();

    if (!map) {
        return { success: false, reason: 'Mapbox map instance not ready' };
    }

    try {
        if (fireMap) {
            fireMap.cur_lat = lat;
            fireMap.cur_long = lng;
            fireMap.coordinates = [lng, lat];
            fireMap.zoom = zoom;
        }
        // Mapbox GL uses [longitude, latitude] order.
        map.jumpTo({ center: [lng, lat], zoom: zoom, essential: true });
        window.dispatchEvent(new Event('resize'));
        return { success: true, method: fireMap ? 'vue_firemap_jumpTo' : 'dom_mapbox_jumpTo' };
    } catch (e) {
        return { success: false, reason: String(e) };
    }
}
"""


def pan_map_to_project(
    page: Page,
    lat: float,
    lng: float,
    zoom: int,
    *,
    max_attempts: int = 15,
    retry_delay: float = 1.0,
) -> None:
    """
    Pan and zoom the Mapbox map via FireMapSim's Vue FireMap component.
    Retries until the map finishes loading.
    """
    for attempt in range(1, max_attempts + 1):
        result = page.evaluate(PAN_MAP_JS, [lat, lng, zoom])
        if result.get("success"):
            print(
                f"  -> Map panned to ({lat}, {lng}) zoom={zoom}  "
                f"[{result.get('method')}, attempt {attempt}]"
            )
            return
        reason = result.get("reason", "unknown")
        print(f"  ... map not ready ({attempt}/{max_attempts}): {reason}")
        time.sleep(retry_delay)

    print("  !  Map pan failed after retries — user can pan manually.")

# ---------------------------------------------------------------------------
# Floating chat overlay injected into the FireMapSim page
# ---------------------------------------------------------------------------

# The overlay HTML is injected once at startup and then updated on each step.
# It sits in a fixed position panel on the right side of the screen so it
# doesn't cover the map controls.

OVERLAY_INIT_JS = """
() => {
    if (document.getElementById('__fsai_overlay__')) return;

    const panel = document.createElement('div');
    panel.id = '__fsai_overlay__';
    panel.setAttribute('style', [
        'all: initial',
        'position: fixed',
        'top: 16px',
        'right: 16px',
        'width: 340px',
        'max-height: 80vh',
        'z-index: 2147483647',
        'display: flex',
        'flex-direction: column',
        'background: #1e1e1e',
        'border-radius: 12px',
        'border-left: 4px solid #ff6600',
        'box-shadow: 0 8px 32px rgba(0,0,0,0.45)',
        'font-family: -apple-system, Segoe UI, Roboto, sans-serif',
        'font-size: 14px',
        'color: #fff',
        'overflow: hidden',
    ].join(' !important; ') + ' !important');

    // Header bar
    const header = document.createElement('div');
    header.setAttribute('style', [
        'all: initial',
        'display: flex',
        'align-items: center',
        'gap: 8px',
        'padding: 10px 14px',
        'background: #2a2a2a',
        'border-bottom: 1px solid #333',
        'font-family: -apple-system, Segoe UI, Roboto, sans-serif',
        'flex-shrink: 0',
    ].join(' !important; ') + ' !important');

    const dot = document.createElement('span');
    dot.setAttribute('style', 'all:initial !important; width:10px !important; height:10px !important; border-radius:50% !important; background:#ff6600 !important; display:inline-block !important; flex-shrink:0 !important;');

    const title = document.createElement('span');
    title.setAttribute('style', 'all:initial !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:13px !important; font-weight:600 !important; color:#fff !important; letter-spacing:0.3px !important;');
    title.textContent = 'FireMapSim AI Co-pilot';

    const stepBadge = document.createElement('span');
    stepBadge.id = '__fsai_step_badge__';
    stepBadge.setAttribute('style', 'all:initial !important; margin-left:auto !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:11px !important; color:#aaa !important;');
    stepBadge.textContent = '';

    header.appendChild(dot);
    header.appendChild(title);
    header.appendChild(stepBadge);

    // Message area
    const msgArea = document.createElement('div');
    msgArea.id = '__fsai_msg_area__';
    msgArea.setAttribute('style', [
        'all: initial',
        'flex: 1',
        'overflow-y: auto',
        'padding: 14px',
        'display: flex',
        'flex-direction: column',
        'gap: 10px',
        'font-family: -apple-system, Segoe UI, Roboto, sans-serif',
        'font-size: 14px',
        'color: #e0e0e0',
        'line-height: 1.5',
        'min-height: 80px',
        'max-height: 50vh',
    ].join(' !important; ') + ' !important');

    const placeholder = document.createElement('div');
    placeholder.setAttribute('style', 'all:initial !important; color:#666 !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:13px !important; text-align:center !important; padding:20px 0 !important;');
    placeholder.textContent = 'Starting guided walkthrough...';
    msgArea.appendChild(placeholder);

    // Button row
    const btnRow = document.createElement('div');
    btnRow.id = '__fsai_btn_row__';
    btnRow.setAttribute('style', [
        'all: initial',
        'display: flex',
        'gap: 8px',
        'justify-content: flex-end',
        'padding: 10px 14px',
        'background: #2a2a2a',
        'border-top: 1px solid #333',
        'flex-shrink: 0',
    ].join(' !important; ') + ' !important');

    panel.appendChild(header);
    panel.appendChild(msgArea);
    panel.appendChild(btnRow);
    (document.body || document.documentElement).appendChild(panel);

    window.__guide_action__ = null;
}
"""

def inject_overlay(page: Page) -> None:
    """Inject the floating chat overlay panel into the page once."""
    try:
        page.evaluate(OVERLAY_INIT_JS)
        print("  -> Floating overlay injected.")
    except Exception as exc:
        print(f"  !  Overlay injection failed: {exc}")


def clean_for_display(text: str) -> str:
    """
    Remove any JSON code fences or raw JSON objects that slipped through
    the system prompt instructions. Also strips markdown bold/italic markers.
    This is a safety net — the prompt changes should prevent this.
    """
    # Remove ```json ... ``` blocks entirely
    text = re.sub(r"```json[\s\S]*?```", "", text, flags=re.IGNORECASE)
    # Remove any remaining ``` fences
    text = re.sub(r"```[\s\S]*?```", "", text)
    # Remove lone backticks
    text = text.replace("`", "")
    # Remove markdown bold/italic
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    # Collapse extra blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def update_overlay(page: Page, turn: int, total: int, reply: str, is_last: bool) -> None:
    """
    Update the floating overlay with the current step's agent reply
    and render Next/Quit buttons. Strips any JSON that slipped through.
    """
    clean_reply = clean_for_display(reply)
    if len(clean_reply) > OVERLAY_MAX_CHARS:
        clean_reply = clean_reply[: OVERLAY_MAX_CHARS].rsplit(" ", 1)[0] + "…"

    next_label = "Finish" if is_last else "Next step →"
    safe_reply = clean_reply.replace("\\", "\\\\").replace("`", "\\`").replace("'", "\\'")

    page.evaluate(
        """([msg, turn, total, nextLabel]) => {
            try {
                window.__guide_action__ = null;

                // Update step badge
                const badge = document.getElementById('__fsai_step_badge__');
                if (badge) badge.textContent = 'Step ' + turn + ' / ' + total;

                // Clear and repopulate message area
                const area = document.getElementById('__fsai_msg_area__');
                if (area) {
                    area.innerHTML = '';

                    // Step label
                    const label = document.createElement('div');
                    label.setAttribute('style', 'all:initial !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:11px !important; font-weight:600 !important; color:#ff6600 !important; text-transform:uppercase !important; letter-spacing:0.5px !important;');
                    label.textContent = 'Step ' + turn + ' of ' + total;
                    area.appendChild(label);

                    // Message text — split on newlines to preserve numbered steps
                    const lines = msg.split('\\n');
                    lines.forEach(line => {
                        if (line.trim() === '') return;
                        const p = document.createElement('div');
                        p.setAttribute('style', 'all:initial !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:13px !important; color:#e0e0e0 !important; line-height:1.55 !important; display:block !important;');
                        p.textContent = line;
                        area.appendChild(p);
                    });

                    // Scroll to bottom
                    area.scrollTop = area.scrollHeight;
                }

                // Rebuild button row
                const btnRow = document.getElementById('__fsai_btn_row__');
                if (btnRow) {
                    btnRow.innerHTML = '';

                    const quitBtn = document.createElement('button');
                    quitBtn.setAttribute('style', 'all:initial !important; background:transparent !important; color:#aaa !important; border:1px solid #555 !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:12px !important; padding:6px 12px !important; border-radius:6px !important; cursor:pointer !important; display:inline-block !important;');
                    quitBtn.textContent = 'Quit';
                    quitBtn.onclick = () => { window.__guide_action__ = 'quit'; };

                    const nextBtn = document.createElement('button');
                    nextBtn.setAttribute('style', 'all:initial !important; background:#ff6600 !important; color:#fff !important; border:none !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:12px !important; font-weight:600 !important; padding:6px 14px !important; border-radius:6px !important; cursor:pointer !important; display:inline-block !important;');
                    nextBtn.textContent = nextLabel;
                    nextBtn.onclick = () => { window.__guide_action__ = 'next'; };

                    btnRow.appendChild(quitBtn);
                    btnRow.appendChild(nextBtn);
                }
            } catch (e) {
                console.error('overlay update error:', e);
                window.__guide_action__ = 'next';
            }
        }""",
        [safe_reply, turn, total, next_label],
    )


def show_overlay_end(page: Page, completed: bool) -> None:
    """Show a final completion message in the overlay."""
    heading = "Walkthrough complete!" if completed else "Walkthrough stopped."
    body = (
        "All steps done. Feel free to keep exploring FireMapSim."
        if completed
        else "You can keep exploring FireMapSim, or close this window."
    )

    page.evaluate(
        """([heading, body]) => {
            try {
                window.__guide_action__ = null;

                const badge = document.getElementById('__fsai_step_badge__');
                if (badge) badge.textContent = '';

                const area = document.getElementById('__fsai_msg_area__');
                if (area) {
                    area.innerHTML = '';

                    const h = document.createElement('div');
                    h.setAttribute('style', 'all:initial !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:14px !important; font-weight:600 !important; color:#fff !important; display:block !important;');
                    h.textContent = heading;
                    area.appendChild(h);

                    const b = document.createElement('div');
                    b.setAttribute('style', 'all:initial !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:13px !important; color:#aaa !important; margin-top:6px !important; display:block !important;');
                    b.textContent = body;
                    area.appendChild(b);
                }

                const btnRow = document.getElementById('__fsai_btn_row__');
                if (btnRow) {
                    btnRow.innerHTML = '';
                    const closeBtn = document.createElement('button');
                    closeBtn.setAttribute('style', 'all:initial !important; background:#ff6600 !important; color:#fff !important; border:none !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:12px !important; font-weight:600 !important; padding:6px 14px !important; border-radius:6px !important; cursor:pointer !important; display:inline-block !important;');
                    closeBtn.textContent = 'Close browser';
                    closeBtn.onclick = () => { window.__guide_action__ = 'close'; };
                    btnRow.appendChild(closeBtn);
                }
            } catch (e) {
                console.error('overlay end error:', e);
                window.__guide_action__ = 'close';
            }
        }""",
        [heading, body],
    )


# ---------------------------------------------------------------------------
# Existing helpers (highlight, caption, wait)
# ---------------------------------------------------------------------------

def chat(message: str) -> str:
    """Send a message to the firesim-ai agent and return the reply."""
    resp = requests.post(API_URL, json={"message": message, "thread_id": THREAD_ID}, timeout=120)
    resp.raise_for_status()
    return resp.json()["reply"]


def detect_step(reply: str) -> str | None:
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


def wait_for_page_action(page: Page) -> str:
    page.wait_for_function(
        "() => window.__guide_action__ === 'next' || window.__guide_action__ === 'quit'",
        timeout=0,
    )
    return page.evaluate("() => window.__guide_action__")


def wait_for_close(page: Page) -> None:
    page.wait_for_function(
        "() => window.__guide_action__ === 'close'",
        timeout=0,
    )


def narrate(reply: str) -> None:
    print("\n" + "-" * 60)
    print(textwrap.fill(clean_for_display(reply), width=78))
    print("-" * 60 + "\n")


# ---------------------------------------------------------------------------
# Demo script
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
    launch_url = firesim_url(PROJECT_LAT, PROJECT_LNG, PROJECT_ZOOM)

    with sync_playwright() as pw:
        # Maximize the real browser window — fixed viewport was cropping the UI.
        browser = pw.chromium.launch(
            headless=False,
            slow_mo=50,
            args=["--start-maximized"],
        )
        context = browser.new_context(no_viewport=True)
        page    = context.new_page()

        print(f"Opening FireMapSim at {launch_url} ...")
        page.goto(launch_url, wait_until="domcontentloaded", timeout=60000)
        # Wait for Mapbox canvas — networkidle can hang on tile streaming.
        try:
            page.wait_for_selector(".mapboxgl-canvas, .map-layer canvas", timeout=30000)
        except Exception:
            print("  !  Map canvas selector not found yet — continuing anyway.")
        print("Page loaded.\n")

        # Let the Vue app and Mapbox finish initializing.
        time.sleep(2)

        # 1. Inject the floating AI overlay (visible for the whole session).
        inject_overlay(page)

        # 2. Pan the map to the Canton, GA project location immediately.
        print(f"Panning map to project location: ({PROJECT_LAT}, {PROJECT_LNG}) ...")
        pan_map_to_project(page, PROJECT_LAT, PROJECT_LNG, PROJECT_ZOOM)
        time.sleep(1)  # let the animation settle

        print("Starting guided walkthrough.")
        print("Use the 'Next step' / 'Quit' buttons in the on-screen overlay to control pacing.\n")

        total = len(DEMO_SCRIPT)
        active_selector: str | None = None
        completed = False

        for turn, user_msg in enumerate(DEMO_SCRIPT, start=1):
            print(f"\n[Turn {turn}/{total}]  User: {user_msg}")

            # Send to agent
            try:
                reply = chat(user_msg)
            except Exception as exc:
                print(f"  x API error: {exc}")
                reply = f"Something went wrong reaching the assistant for this step. Please continue manually."

            narrate(reply)

            # Detect UI element to highlight
            step_key = detect_step(reply)
            if step_key and step_key in STEP_SELECTORS:
                selector = STEP_SELECTORS[step_key]
                highlight_on(page, selector, step_key)
                active_selector = selector
            else:
                print("  (no specific UI element detected for this step)")
                active_selector = None

            # Update the on-screen overlay with the agent's plain-English reply
            is_last = turn == total
            try:
                update_overlay(page, turn, total, reply, is_last)
                action = wait_for_page_action(page)
            except Exception as exc:
                print(f"  !  Overlay error, continuing automatically: {exc}")
                action = "next"

            # Remove highlight before moving to next step
            if active_selector:
                highlight_off(page, active_selector)

            if action == "quit":
                print("\nWalkthrough stopped early by user.")
                break
        else:
            completed = True
            print("\nGuided walkthrough complete.")

        # Final screen
        try:
            show_overlay_end(page, completed)
            wait_for_close(page)
        except Exception as exc:
            print(f"  !  End screen error: {exc}")

        browser.close()


if __name__ == "__main__":
    main()
