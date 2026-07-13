"""
playwright/guide.py

FireMapSim UI walkthrough guide.
Launches or attaches to https://firesim.cs.gsu.edu/,
then highlights UI fields as the agent narrates each setup step.

Usage:
    python playwright/guide.py

The script:
  1. Opens FireMapSim in a visible browser window.
  2. Injects a full-height right sidebar so the agent is visible on-screen.
  3. Pans the map to the project location via Mapbox GL (Vue FireMap component).
  4. Sends each demo message to the local firesim-ai API (localhost:8000/chat).
  5. Parses the agent reply to detect which UI element to highlight.
  6. Scrolls to + visually highlights that element on the live page.
  7. Shows agent responses in the sidebar (no raw JSON, no truncation).
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
SESSION_URL  = "http://localhost:8000/api/session"

# Prefer FIRESIM_SESSION_ID from demo/run_demo.py; otherwise issue a new one.
_SESSION_ID = os.environ.get("FIRESIM_SESSION_ID")

# Canton, GA prescribed burn center coordinates
PROJECT_LAT = 34.2367621
PROJECT_LNG = -84.4907621
PROJECT_ZOOM = 13  # zoom level — 13 gives a good neighbourhood view

# Sidebar width — main page content is shifted left to make room.
SIDEBAR_WIDTH = 360

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
    # Most specific UI control names first; ignition before generic "duration".
    ("set line ignition",    "set_line_ignition"),
    ("set point ignition",   "set_point_ignition"),
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
# Right sidebar panel injected into the FireMapSim page
# ---------------------------------------------------------------------------

def inject_sidebar(page: Page) -> None:
    """Inject a full-height right sidebar and shift page content left."""
    try:
        page.evaluate(
            """(width) => {
                if (document.getElementById('__fsai_sidebar__')) return;

                document.documentElement.style.setProperty('margin-right', width + 'px', 'important');
                document.body.style.setProperty('margin-right', width + 'px', 'important');

                const panel = document.createElement('div');
                panel.id = '__fsai_sidebar__';
                panel.setAttribute('style', [
                    'all: initial',
                    'position: fixed',
                    'top: 0',
                    'right: 0',
                    'bottom: 0',
                    'width: ' + width + 'px',
                    'height: 100vh',
                    'z-index: 2147483647',
                    'display: flex',
                    'flex-direction: column',
                    'background: #1e1e1e',
                    'border-left: 3px solid #ff6600',
                    'box-shadow: -4px 0 24px rgba(0,0,0,0.35)',
                    'font-family: -apple-system, Segoe UI, Roboto, sans-serif',
                    'font-size: 14px',
                    'color: #fff',
                    'overflow: hidden',
                    'box-sizing: border-box',
                ].join(' !important; ') + ' !important');

                const header = document.createElement('div');
                header.setAttribute('style', [
                    'all: initial', 'display: flex', 'align-items: center', 'gap: 8px',
                    'padding: 12px 16px', 'background: #2a2a2a', 'border-bottom: 1px solid #333',
                    'font-family: -apple-system, Segoe UI, Roboto, sans-serif', 'flex-shrink: 0',
                    'box-sizing: border-box',
                ].join(' !important; ') + ' !important');

                const dot = document.createElement('span');
                dot.setAttribute('style', 'all:initial !important; width:10px !important; height:10px !important; border-radius:50% !important; background:#ff6600 !important; display:inline-block !important;');
                const title = document.createElement('span');
                title.setAttribute('style', 'all:initial !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:13px !important; font-weight:600 !important; color:#fff !important;');
                title.textContent = 'FireMapSim AI Co-pilot';
                const stepBadge = document.createElement('span');
                stepBadge.id = '__fsai_step_badge__';
                stepBadge.setAttribute('style', 'all:initial !important; margin-left:auto !important; font-size:11px !important; color:#aaa !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important;');
                header.appendChild(dot);
                header.appendChild(title);
                header.appendChild(stepBadge);

                const msgArea = document.createElement('div');
                msgArea.id = '__fsai_msg_area__';
                msgArea.setAttribute('style', [
                    'all: initial', 'flex: 1 1 auto', 'overflow-y: auto', 'overflow-x: hidden',
                    'padding: 16px', 'display: flex', 'flex-direction: column', 'gap: 10px',
                    'font-family: -apple-system, Segoe UI, Roboto, sans-serif',
                    'font-size: 14px', 'color: #e0e0e0', 'line-height: 1.55',
                    'min-height: 0', 'box-sizing: border-box',
                ].join(' !important; ') + ' !important');

                const placeholder = document.createElement('div');
                placeholder.setAttribute('style', 'all:initial !important; color:#666 !important; font-size:13px !important; text-align:center !important; padding:24px 0 !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important;');
                placeholder.textContent = 'Starting guided walkthrough...';
                msgArea.appendChild(placeholder);

                const btnRow = document.createElement('div');
                btnRow.id = '__fsai_btn_row__';
                btnRow.setAttribute('style', [
                    'all: initial', 'display: flex', 'gap: 8px', 'justify-content: flex-end',
                    'padding: 12px 16px', 'background: #2a2a2a', 'border-top: 1px solid #333',
                    'flex-shrink: 0', 'box-sizing: border-box',
                ].join(' !important; ') + ' !important');

                panel.appendChild(header);
                panel.appendChild(msgArea);
                panel.appendChild(btnRow);
                (document.body || document.documentElement).appendChild(panel);
                window.__guide_action__ = null;
                window.dispatchEvent(new Event('resize'));
            }""",
            SIDEBAR_WIDTH,
        )
        print("  -> Sidebar injected.")
    except Exception as exc:
        print(f"  !  Sidebar injection failed: {exc}")


def clean_for_display(text: str) -> str:
    """
    Prepare agent text for display: strip JSON fences, markdown, and any
    double-escaped quotes that slipped through serialization.
    """
    text = re.sub(r"```json[\s\S]*?```", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = text.replace("`", "")
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*", r"\1", text)
    # Fix double-escaped quotes from legacy manual JS escaping.
    text = text.replace("\\'", "'").replace('\\"', '"')
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def update_sidebar(page: Page, turn: int, total: int, reply: str, is_last: bool) -> None:
    """Update the sidebar with the current step text and Next/Quit buttons."""
    display_text = clean_for_display(reply)
    next_label = "Finish" if is_last else "Next step →"

    # Playwright JSON-serializes arguments — pass plain strings, no manual escaping.
    page.evaluate(
        """(data) => {
            const { msg, turn, total, nextLabel } = data;
            try {
                window.__guide_action__ = null;

                const badge = document.getElementById('__fsai_step_badge__');
                if (badge) badge.textContent = 'Step ' + turn + ' / ' + total;

                const area = document.getElementById('__fsai_msg_area__');
                if (area) {
                    area.innerHTML = '';

                    const label = document.createElement('div');
                    label.setAttribute('style', 'all:initial !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:11px !important; font-weight:600 !important; color:#ff6600 !important; text-transform:uppercase !important; letter-spacing:0.5px !important; margin-bottom:4px !important;');
                    label.textContent = 'Step ' + turn + ' of ' + total;
                    area.appendChild(label);

                    const lines = msg.split('\\n');
                    for (const line of lines) {
                        if (!line.trim()) continue;
                        const p = document.createElement('div');
                        p.setAttribute('style', 'all:initial !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:13px !important; color:#e0e0e0 !important; line-height:1.55 !important; display:block !important; margin-bottom:6px !important; word-wrap:break-word !important; overflow-wrap:break-word !important;');
                        p.textContent = line;
                        area.appendChild(p);
                    }
                    area.scrollTop = 0;
                }

                const btnRow = document.getElementById('__fsai_btn_row__');
                if (btnRow) {
                    btnRow.innerHTML = '';
                    const quitBtn = document.createElement('button');
                    quitBtn.setAttribute('style', 'all:initial !important; background:transparent !important; color:#aaa !important; border:1px solid #555 !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:12px !important; padding:6px 12px !important; border-radius:6px !important; cursor:pointer !important;');
                    quitBtn.textContent = 'Quit';
                    quitBtn.onclick = () => { window.__guide_action__ = 'quit'; };
                    const nextBtn = document.createElement('button');
                    nextBtn.setAttribute('style', 'all:initial !important; background:#ff6600 !important; color:#fff !important; border:none !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:12px !important; font-weight:600 !important; padding:6px 14px !important; border-radius:6px !important; cursor:pointer !important;');
                    nextBtn.textContent = nextLabel;
                    nextBtn.onclick = () => { window.__guide_action__ = 'next'; };
                    btnRow.appendChild(quitBtn);
                    btnRow.appendChild(nextBtn);
                }
            } catch (e) {
                console.error('sidebar update error:', e);
                window.__guide_action__ = 'next';
            }
        }""",
        {"msg": display_text, "turn": turn, "total": total, "nextLabel": next_label},
    )


def show_sidebar_end(page: Page, completed: bool) -> None:
    """Show a final completion message in the sidebar."""
    heading = "Walkthrough complete!" if completed else "Walkthrough stopped."
    body = (
        "All steps done. Feel free to keep exploring FireMapSim."
        if completed
        else "You can keep exploring FireMapSim, or close this window."
    )

    page.evaluate(
        """(data) => {
            const { heading, body } = data;
            try {
                window.__guide_action__ = null;
                const badge = document.getElementById('__fsai_step_badge__');
                if (badge) badge.textContent = '';
                const area = document.getElementById('__fsai_msg_area__');
                if (area) {
                    area.innerHTML = '';
                    const h = document.createElement('div');
                    h.setAttribute('style', 'all:initial !important; font-size:14px !important; font-weight:600 !important; color:#fff !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important;');
                    h.textContent = heading;
                    area.appendChild(h);
                    const b = document.createElement('div');
                    b.setAttribute('style', 'all:initial !important; font-size:13px !important; color:#aaa !important; margin-top:8px !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important;');
                    b.textContent = body;
                    area.appendChild(b);
                }
                const btnRow = document.getElementById('__fsai_btn_row__');
                if (btnRow) {
                    btnRow.innerHTML = '';
                    const closeBtn = document.createElement('button');
                    closeBtn.setAttribute('style', 'all:initial !important; background:#ff6600 !important; color:#fff !important; border:none !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:12px !important; font-weight:600 !important; padding:6px 14px !important; border-radius:6px !important; cursor:pointer !important;');
                    closeBtn.textContent = 'Close browser';
                    closeBtn.onclick = () => { window.__guide_action__ = 'close'; };
                    btnRow.appendChild(closeBtn);
                }
            } catch (e) {
                window.__guide_action__ = 'close';
            }
        }""",
        {"heading": heading, "body": body},
    )


# ---------------------------------------------------------------------------
# Existing helpers (highlight, caption, wait)
# ---------------------------------------------------------------------------

def get_session_id() -> str:
    global _SESSION_ID
    if _SESSION_ID:
        return _SESSION_ID
    resp = requests.post(SESSION_URL, timeout=30)
    resp.raise_for_status()
    _SESSION_ID = resp.json()["session_id"]
    print(f"  Issued session_id={_SESSION_ID[:12]}… (set FIRESIM_SESSION_ID to share with demo)")
    return _SESSION_ID


def chat(message: str) -> str:
    """Send a message to the firesim-ai agent and return the reply."""
    session_id = get_session_id()
    resp = requests.post(
        API_URL,
        json={"message": message},
        headers={"X-Session-Id": session_id},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["reply"]


def detect_step(reply: str, expected: str | None = None) -> str | None:
    """Return highlight key — prefer the scripted per-step target over LLM keywords."""
    if expected and expected in STEP_SELECTORS:
        return expected
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

# Each step maps a user message to the one UI control we highlight.
# This avoids keyword mismatches when the agent mentions multiple fields.
DEMO_STEPS: list[dict[str, str | None]] = [
    {
        "message": "I want to set up a prescribed burn simulation near Canton, GA.",
        "highlight": None,
    },
    {
        "message": "What cell resolution and cell space dimension should I use?",
        "highlight": "cell_resolution",
    },
    {
        "message": "How do I set the project location on the map?",
        "highlight": "set_project_location",
    },
    {
        "message": "Where do I enter wind speed and wind direction?",
        "highlight": "wind_speed",
    },
    {
        "message": "What simulation duration should I use for a prescribed burn?",
        "highlight": "simulation_duration",
    },
    {
        "message": "How do I get the terrain and fuel data for this area?",
        "highlight": "get_terrain_fuel",
    },
    {
        "message": "Walk me through setting an ignition line.",
        "highlight": "set_line_ignition",
    },
    {
        "message": "How do I start the simulation once everything is configured?",
        "highlight": "start_simulation",
    },
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

        # 1. Inject the right sidebar (visible for the whole session).
        inject_sidebar(page)

        # 2. Pan the map to the Canton, GA project location immediately.
        print(f"Panning map to project location: ({PROJECT_LAT}, {PROJECT_LNG}) ...")
        pan_map_to_project(page, PROJECT_LAT, PROJECT_LNG, PROJECT_ZOOM)
        time.sleep(1)  # let the animation settle

        print("Starting guided walkthrough.")
        print("Use the 'Next step' / 'Quit' buttons in the sidebar to control pacing.\n")

        total = len(DEMO_STEPS)
        active_selector: str | None = None
        completed = False

        for turn, step in enumerate(DEMO_STEPS, start=1):
            user_msg = str(step["message"])
            expected_highlight = step.get("highlight")
            expected_key = expected_highlight if isinstance(expected_highlight, str) else None
            print(f"\n[Turn {turn}/{total}]  User: {user_msg}")

            # Send to agent
            try:
                reply = chat(user_msg)
            except Exception as exc:
                print(f"  x API error: {exc}")
                reply = "Something went wrong reaching the assistant for this step. Please continue manually."

            narrate(reply)

            # Highlight the control tied to this demo step (not LLM keyword guesswork).
            step_key = detect_step(reply, expected=expected_key)
            if step_key and step_key in STEP_SELECTORS:
                selector = STEP_SELECTORS[step_key]
                highlight_on(page, selector, str(step_key))
                active_selector = selector
                print(f"  (scripted highlight: {step_key})")
            else:
                print("  (no highlight for this step)")
                active_selector = None

            # Update the sidebar with the agent's plain-English reply
            is_last = turn == total
            try:
                update_sidebar(page, turn, total, reply, is_last)
                action = wait_for_page_action(page)
            except Exception as exc:
                print(f"  !  Sidebar error, continuing automatically: {exc}")
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
            show_sidebar_end(page, completed)
            wait_for_close(page)
        except Exception as exc:
            print(f"  !  End screen error: {exc}")

        browser.close()


if __name__ == "__main__":
    main()
