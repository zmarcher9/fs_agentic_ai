"""
playwright/guide.py

FireMapSim live co-pilot.
Launches or attaches to the real FireMapSim page (FIREMAP_URL), injects a
free-text chat sidebar wired to the local firesim-ai API, and highlights
the UI control the agent is talking about as you chat.

Usage:
    python playwright/guide.py

The script:
  1. Opens FireMapSim in a visible browser window.
  2. Injects a collapsed floating launcher button; click it to open the sidebar.
  3. Pans the map to the project location via Mapbox GL (Vue FireMap component).
  4. Lets you type any message into the sidebar and sends it to the local
     firesim-ai API (localhost:8000/chat).
  5. Parses the agent reply to detect which UI element it's talking about.
  6. Scrolls to + visually highlights that element on the live page.
  7. Appends the agent's reply to the chat transcript in the sidebar.
  8. Keeps chatting until you close the browser window.

Requires:
    pip install playwright requests
    playwright install chromium
"""

import sys
import os
import re
import time
import textwrap
import requests
from playwright.sync_api import sync_playwright, Page, Locator

# Add the project root to sys.path so we can import app.config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import get_settings

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_settings = get_settings()
FIRESIM_BASE = _settings.firemap_url
API_URL = f"{_settings.api_base_url.rstrip('/')}/chat"
SESSION_URL = f"{_settings.api_base_url.rstrip('/')}/api/session"

# Prefer FIRESIM_SESSION_ID from demo/run_demo.py; otherwise issue a new one.
_SESSION_ID = os.environ.get("FIRESIM_SESSION_ID")

# Canton, GA prescribed burn center coordinates
PROJECT_LAT = 34.2367621
PROJECT_LNG = -84.4907621
PROJECT_ZOOM = 13  # zoom level — 13 gives a good neighbourhood view

# Sidebar width — main page content is shifted left to make room.
SIDEBAR_WIDTH = 360

WELCOME_MESSAGE = (
    "Ask me anything about setting up your prescribed burn simulation - "
    "location, wind, cell resolution, ignition lines, and more."
)

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

# ---------------------------------------------------------------------------
# Map panning via Mapbox GL (FireMapSim Vue component)
# ---------------------------------------------------------------------------

def firesim_url(lat: float, lng: float, zoom: int) -> str:
    """Open the sim UI directly; query params seed the initial map center."""
    return f"{FIRESIM_BASE}?lat={lat}&lng={lng}&zoom={zoom}"


PAN_MAP_JS = """
([lat, lng, zoom]) => {
    // #app.__vue__ is unreliable: when a descendant component's root render
    // element happens to be the same DOM node as #app (a Vue 2 quirk), that
    // descendant's instance overwrites __vue__ there, and its $children may
    // be empty — the real app tree is orphaned from that starting point.
    // Scan every element instead of trusting #app to hold the true root.
    function findFireMapAnywhere() {
        const all = document.querySelectorAll('*');
        for (const el of all) {
            const vm = el.__vue__;
            if (vm && vm.$options && vm.$options.name === 'FireMap') return vm;
        }
        return null;
    }

    // The live Mapbox instance isn't necessarily on FireMap itself — it may
    // live on a nested child component (e.g. a GlMap wrapper). Search the
    // whole subtree for whichever component actually holds it.
    function findMapInstance(vm, depth) {
        if (!vm || depth > 12) return null;
        if (vm.map && typeof vm.map.jumpTo === 'function') return vm.map;
        const kids = vm.$children || [];
        for (let i = 0; i < kids.length; i++) {
            const found = findMapInstance(kids[i], depth + 1);
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

    const fireMap = findFireMapAnywhere();
    let map = fireMap ? findMapInstance(fireMap, 0) : null;
    if (!map) map = findMapboxOnDom();

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
    """
    Inject a collapsed floating launcher button plus a hidden right sidebar
    chat panel: a scrolling transcript, a text input, and a Send button.
    Submitting a message sets window.__fsai_pending__; main() polls for it,
    calls the API, then hands the reply to window.__fsai_append_agent__.
    """
    try:
        page.evaluate(
            """(args) => {
                const [width, welcome] = args;
                if (document.getElementById('__fsai_sidebar__')) return;

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
                    'background: #ffffff',
                    'border-left: 3px solid #ff6600',
                    'box-shadow: -4px 0 24px rgba(0,0,0,0.18)',
                    'font-family: -apple-system, Segoe UI, Roboto, sans-serif',
                    'font-size: 14px',
                    'color: #1a1a1a',
                    'overflow: hidden',
                    'box-sizing: border-box',
                    'transform: translateX(100%)',
                    'transition: transform 0.25s ease',
                    'visibility: hidden',
                ].join(' !important; ') + ' !important');

                const header = document.createElement('div');
                header.setAttribute('style', [
                    'all: initial', 'display: flex', 'align-items: center', 'gap: 8px',
                    'padding: 12px 16px', 'background: #f7f7f7', 'border-bottom: 1px solid #e5e5e5',
                    'font-family: -apple-system, Segoe UI, Roboto, sans-serif', 'flex-shrink: 0',
                    'box-sizing: border-box',
                ].join(' !important; ') + ' !important');

                const dot = document.createElement('span');
                dot.setAttribute('style', 'all:initial !important; width:10px !important; height:10px !important; border-radius:50% !important; background:#ff6600 !important; display:inline-block !important;');
                const title = document.createElement('span');
                title.setAttribute('style', 'all:initial !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:13px !important; font-weight:600 !important; color:#1a1a1a !important;');
                title.textContent = 'FireMapSim AI Co-pilot';
                const collapseBtn = document.createElement('button');
                collapseBtn.setAttribute('style', 'all:initial !important; margin-left:auto !important; background:transparent !important; border:none !important; color:#888 !important; font-size:18px !important; line-height:1 !important; cursor:pointer !important; padding:0 2px !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important;');
                collapseBtn.textContent = String.fromCharCode(10005);
                collapseBtn.title = 'Collapse';
                collapseBtn.onclick = () => window.__fsai_toggle__(false);
                header.appendChild(dot);
                header.appendChild(title);
                header.appendChild(collapseBtn);

                const msgArea = document.createElement('div');
                msgArea.id = '__fsai_msg_area__';
                msgArea.setAttribute('style', [
                    'all: initial', 'flex: 1 1 auto', 'overflow-y: auto', 'overflow-x: hidden',
                    'padding: 16px', 'display: flex', 'flex-direction: column', 'gap: 10px',
                    'font-family: -apple-system, Segoe UI, Roboto, sans-serif',
                    'font-size: 14px', 'color: #333', 'line-height: 1.55',
                    'min-height: 0', 'box-sizing: border-box',
                ].join(' !important; ') + ' !important');

                const inputRow = document.createElement('div');
                inputRow.id = '__fsai_input_row__';
                inputRow.setAttribute('style', [
                    'all: initial', 'display: flex', 'gap: 8px', 'align-items: center',
                    'padding: 12px 16px', 'background: #f7f7f7', 'border-top: 1px solid #e5e5e5',
                    'flex-shrink: 0', 'box-sizing: border-box',
                ].join(' !important; ') + ' !important');

                const input = document.createElement('input');
                input.id = '__fsai_input__';
                input.type = 'text';
                input.placeholder = 'Ask about your burn setup...';
                input.setAttribute('style', [
                    'all: initial', 'flex: 1 1 auto', 'min-width: 0', 'padding: 8px 10px',
                    'border: 1px solid #ccc', 'border-radius: 6px',
                    'font-family: -apple-system, Segoe UI, Roboto, sans-serif', 'font-size: 13px',
                    'color: #1a1a1a', 'background: #ffffff', 'box-sizing: border-box',
                ].join(' !important; ') + ' !important');

                const sendBtn = document.createElement('button');
                sendBtn.id = '__fsai_send__';
                sendBtn.textContent = 'Send';
                sendBtn.setAttribute('style', [
                    'all: initial', 'background: #ff6600', 'color: #fff', 'border: none',
                    'font-family: -apple-system, Segoe UI, Roboto, sans-serif', 'font-size: 12px',
                    'font-weight: 600', 'padding: 8px 14px', 'border-radius: 6px', 'cursor: pointer',
                    'flex-shrink: 0', 'box-sizing: border-box',
                ].join(' !important; ') + ' !important');

                inputRow.appendChild(input);
                inputRow.appendChild(sendBtn);

                panel.appendChild(header);
                panel.appendChild(msgArea);
                panel.appendChild(inputRow);
                (document.body || document.documentElement).appendChild(panel);

                const launcher = document.createElement('button');
                launcher.id = '__fsai_launcher__';
                launcher.setAttribute('style', [
                    'all: initial', 'position: fixed', 'bottom: 24px', 'right: 24px',
                    'width: 56px', 'height: 56px', 'border-radius: 50%',
                    'background: #ff6600', 'box-shadow: 0 4px 16px rgba(0,0,0,0.3)',
                    'display: flex', 'align-items: center', 'justify-content: center',
                    'cursor: pointer', 'z-index: 2147483647', 'border: none',
                    'font-size: 26px', 'box-sizing: border-box',
                ].join(' !important; ') + ' !important');
                launcher.title = 'Open FireMapSim AI Co-pilot';
                launcher.textContent = String.fromCodePoint(128293);

                const badge = document.createElement('span');
                badge.id = '__fsai_badge__';
                badge.setAttribute('style', 'all:initial !important; position:absolute !important; top:-2px !important; right:-2px !important; width:14px !important; height:14px !important; border-radius:50% !important; background:#ff3b30 !important; border:2px solid #fff !important; display:none !important; box-sizing:border-box !important;');
                launcher.appendChild(badge);
                launcher.onclick = () => window.__fsai_toggle__(true);
                (document.body || document.documentElement).appendChild(launcher);

                window.__fsai_expanded__ = false;
                window.__fsai_toggle__ = function(expand) {
                    const p = document.getElementById('__fsai_sidebar__');
                    const l = document.getElementById('__fsai_launcher__');
                    const b = document.getElementById('__fsai_badge__');
                    if (!p || !l) return;
                    window.__fsai_expanded__ = expand;
                    if (expand) {
                        document.documentElement.style.setProperty('margin-right', width + 'px', 'important');
                        document.body.style.setProperty('margin-right', width + 'px', 'important');
                        p.style.setProperty('visibility', 'visible', 'important');
                        p.style.setProperty('transform', 'translateX(0)', 'important');
                        l.style.setProperty('display', 'none', 'important');
                        if (b) b.style.setProperty('display', 'none', 'important');
                        const inp = document.getElementById('__fsai_input__');
                        if (inp) inp.focus();
                    } else {
                        document.documentElement.style.setProperty('margin-right', '0px', 'important');
                        document.body.style.setProperty('margin-right', '0px', 'important');
                        p.style.setProperty('transform', 'translateX(100%)', 'important');
                        p.style.setProperty('visibility', 'hidden', 'important');
                        l.style.setProperty('display', 'flex', 'important');
                    }
                    window.dispatchEvent(new Event('resize'));
                };

                // ---- chat transcript + input wiring ----------------------

                window.__fsai_pending__ = null;   // set by trySend(); read+cleared by Python
                window.__fsai_busy__ = false;      // true while waiting on an API reply

                function scrollBottom() {
                    const area = document.getElementById('__fsai_msg_area__');
                    if (area) area.scrollTop = area.scrollHeight;
                }

                function appendBubble(text, role) {
                    const area = document.getElementById('__fsai_msg_area__');
                    if (!area) return;
                    const wrap = document.createElement('div');
                    wrap.setAttribute('style', [
                        'all: initial', 'display: flex',
                        'justify-content: ' + (role === 'user' ? 'flex-end' : 'flex-start'),
                    ].join(' !important; ') + ' !important');
                    const bg = role === 'user' ? '#ff6600' : (role === 'error' ? '#fdecea' : '#f1f1f1');
                    const color = role === 'user' ? '#ffffff' : (role === 'error' ? '#b3261e' : '#1a1a1a');
                    const bubble = document.createElement('div');
                    bubble.setAttribute('style', [
                        'all: initial', 'max-width: 85%', 'padding: 8px 12px', 'border-radius: 12px',
                        'background: ' + bg, 'color: ' + color,
                        'font-family: -apple-system, Segoe UI, Roboto, sans-serif', 'font-size: 13px',
                        'line-height: 1.5', 'white-space: pre-wrap', 'word-wrap: break-word',
                        'box-sizing: border-box',
                    ].join(' !important; ') + ' !important');
                    bubble.textContent = text;
                    wrap.appendChild(bubble);
                    area.appendChild(wrap);
                    scrollBottom();
                }

                function showTyping() {
                    removeTyping();
                    const area = document.getElementById('__fsai_msg_area__');
                    if (!area) return;
                    const wrap = document.createElement('div');
                    wrap.id = '__fsai_typing__';
                    wrap.setAttribute('style', 'all:initial !important; display:flex !important; justify-content:flex-start !important;');
                    const bubble = document.createElement('div');
                    bubble.setAttribute('style', 'all:initial !important; padding:8px 12px !important; border-radius:12px !important; background:#f1f1f1 !important; color:#999 !important; font-family:-apple-system,Segoe UI,Roboto,sans-serif !important; font-size:13px !important; font-style:italic !important;');
                    bubble.textContent = 'Thinking...';
                    wrap.appendChild(bubble);
                    area.appendChild(wrap);
                    scrollBottom();
                }

                function removeTyping() {
                    const t = document.getElementById('__fsai_typing__');
                    if (t) t.remove();
                }

                function setBusy(busy) {
                    window.__fsai_busy__ = busy;
                    const inp = document.getElementById('__fsai_input__');
                    const btn = document.getElementById('__fsai_send__');
                    if (inp) inp.disabled = busy;
                    if (btn) btn.disabled = busy;
                    if (busy) showTyping(); else removeTyping();
                }

                function flagUnread() {
                    if (!window.__fsai_expanded__) {
                        const b = document.getElementById('__fsai_badge__');
                        if (b) b.style.setProperty('display', 'block', 'important');
                    }
                }

                window.__fsai_append_agent__ = function(text) {
                    setBusy(false);
                    appendBubble(text, 'agent');
                    flagUnread();
                };
                window.__fsai_append_error__ = function(text) {
                    setBusy(false);
                    appendBubble(text, 'error');
                    flagUnread();
                };

                function trySend() {
                    if (window.__fsai_busy__) return;
                    const inp = document.getElementById('__fsai_input__');
                    if (!inp) return;
                    const val = (inp.value || '').trim();
                    if (!val) return;
                    inp.value = '';
                    appendBubble(val, 'user');
                    setBusy(true);
                    window.__fsai_pending__ = val;
                }

                sendBtn.onclick = trySend;
                input.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') { e.preventDefault(); trySend(); }
                });

                appendBubble(welcome, 'agent');
            }""",
            [SIDEBAR_WIDTH, WELCOME_MESSAGE],
        )
        print("  -> Sidebar injected (collapsed).")
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


def wait_for_user_message(page: Page) -> str:
    """Block until the sidebar's Send button (or Enter) sets a pending message."""
    page.wait_for_function("() => window.__fsai_pending__ !== null", timeout=0)
    msg = page.evaluate("() => window.__fsai_pending__")
    page.evaluate("() => { window.__fsai_pending__ = null; }")
    return msg


def append_agent_reply(page: Page, text: str) -> None:
    page.evaluate("(t) => window.__fsai_append_agent__(t)", text)


def append_agent_error(page: Page, text: str) -> None:
    page.evaluate("(t) => window.__fsai_append_error__(t)", text)


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


def narrate(reply: str) -> None:
    print("\n" + "-" * 60)
    print(textwrap.fill(clean_for_display(reply), width=78))
    print("-" * 60 + "\n")


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

        # 1. Inject the collapsed launcher button + hidden chat sidebar.
        inject_sidebar(page)

        # 2. Pan the map to the Canton, GA project location immediately.
        print(f"Panning map to project location: ({PROJECT_LAT}, {PROJECT_LNG}) ...")
        pan_map_to_project(page, PROJECT_LAT, PROJECT_LNG, PROJECT_ZOOM)
        time.sleep(1)  # let the animation settle

        print("Ready. Click the orange button (bottom-right) to open the co-pilot")
        print("and type a message. Close the browser window to end the session.\n")

        active_selector: str | None = None

        while True:
            try:
                user_msg = wait_for_user_message(page)
            except Exception:
                break  # page/browser was closed

            print(f"\nUser: {user_msg}")

            try:
                reply = chat(user_msg)
            except Exception as exc:
                print(f"  x API error: {exc}")
                try:
                    append_agent_error(page, "Sorry, I ran into a problem reaching the assistant. Please try again.")
                except Exception:
                    break
                continue

            display_text = clean_for_display(reply)
            narrate(reply)

            # Clear the previous highlight before applying the next one.
            if active_selector:
                highlight_off(page, active_selector)
                active_selector = None

            step_key = detect_step(reply)
            if step_key and step_key in STEP_SELECTORS:
                selector = STEP_SELECTORS[step_key]
                highlight_on(page, selector, str(step_key))
                active_selector = selector
            else:
                print("  (no highlight for this reply)")

            try:
                append_agent_reply(page, display_text)
            except Exception:
                break

        print("\nSession ended (browser closed).")
        try:
            browser.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
