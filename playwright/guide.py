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
  3. Lets you type any message into the sidebar and sends it to the local
     firesim-ai API (localhost:8000/chat).
  4. Parses the agent reply to detect which UI element it's talking about.
  5. Scrolls to + visually highlights that element on the live page.
  6. Appends the agent's reply to the chat transcript in the sidebar.
  7. Keeps chatting until you close the browser window.

Requires:
    pip install playwright requests
    playwright install chromium
"""

import sys
import os
import re
import textwrap
import time

from playwright.sync_api import sync_playwright

# Add the project root to sys.path so we can import app.config and playwright_guide.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import get_settings
from app.core.map_bounds import DEFAULT_ZOOM
from playwright_guide.api_client import chat as api_chat
from playwright_guide.highlighting import STEP_SELECTORS, detect_step, highlight_off, highlight_on
from playwright_guide.map_sync import pan_map_live
from playwright_guide.sidebar import (
    append_agent_error,
    append_agent_reply,
    inject_sidebar,
    wait_for_user_message,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_settings = get_settings()
FIRESIM_BASE = _settings.firemap_url

# Sidebar width — main page content is shifted left to make room.
SIDEBAR_WIDTH = 360

WELCOME_MESSAGE = (
    "Ask me anything about setting up your prescribed burn simulation - "
    "location, wind, cell resolution, ignition lines, and more."
)


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


def narrate(reply: str) -> None:
    print("\n" + "-" * 60)
    print(textwrap.fill(clean_for_display(reply), width=78))
    print("-" * 60 + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    with sync_playwright() as pw:
        # Maximize the real browser window — fixed viewport was cropping the UI.
        browser = pw.chromium.launch(
            headless=False,
            slow_mo=50,
            args=["--start-maximized"],
        )
        context = browser.new_context(no_viewport=True)
        page    = context.new_page()

        print(f"Opening FireMapSim at {FIRESIM_BASE} ...")
        # No lat/lng/zoom seeded here — FireMapSim opens at its own default
        # view; the user or agent moves the map from there via chat.
        page.goto(FIRESIM_BASE, wait_until="domcontentloaded", timeout=60000)
        # Wait for Mapbox canvas — networkidle can hang on tile streaming.
        try:
            page.wait_for_selector(".mapboxgl-canvas, .map-layer canvas", timeout=30000)
        except Exception:
            print("  !  Map canvas selector not found yet — continuing anyway.")
        print("Page loaded.\n")

        # Let the Vue app and Mapbox finish initializing.
        time.sleep(2)

        # Inject the collapsed launcher button + hidden chat sidebar.
        inject_sidebar(page, SIDEBAR_WIDTH, WELCOME_MESSAGE)

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
                response = api_chat(user_msg)
            except Exception as exc:
                print(f"  x API error: {exc}")
                try:
                    append_agent_error(page, "Sorry, I ran into a problem reaching the assistant. Please try again.")
                except Exception:
                    break
                continue

            reply = response["reply"]
            display_text = clean_for_display(reply)
            narrate(reply)

            # The agent's navigate_map call moved its own headless tab, not
            # this page — re-pan here so what the user is looking at moves too.
            navigated_to = response.get("navigated_to")
            if navigated_to:
                pan_map_live(
                    page,
                    navigated_to["lat"],
                    navigated_to["lon"],
                    navigated_to.get("zoom") or DEFAULT_ZOOM,
                )

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
