"""
playwright/guide.py

FireMapSim live Q&A helper.
Launches the real FireMapSim page (FIREMAP_URL), injects a free-text chat
sidebar wired to the local firesim-ai API, and highlights the UI control
the agent is talking about as you chat. The agent only explains and points
— it never moves the map or fills in fields; you operate the page yourself.

Usage:
    python playwright/guide.py

The script:
  1. Opens FireMapSim in a visible browser window.
  2. Injects a collapsed floating launcher button; click it to open the sidebar.
  3. Lets you type any message into the sidebar and sends it to the local
     firesim-ai API (localhost:8000/chat).
  4. Appends the agent's reply to the chat transcript in the sidebar.
  5. Scrolls to + outlines the control the reply is about (the first key in
     /chat's `highlight` list that has a selector).
  6. Keeps chatting until you close the browser window. Page reloads are
     fine — the sidebar is re-injected.

Requires (from the project root):
    python -m pip install -r requirements.txt
    python -m playwright install chromium
    the API running (python -m uvicorn api.main:app --port 8000)
"""

import sys
import os
import textwrap
import time

from playwright.sync_api import sync_playwright

# Add the project root to sys.path so we can import app.config and playwright_guide.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import get_settings
from app.core.text_format import strip_markdown
from playwright_guide.api_client import chat as api_chat
from playwright_guide.highlighting import STEP_SELECTORS, highlight_off, highlight_on, pick_highlight
from playwright_guide.sidebar import (
    append_agent_error,
    append_agent_reply,
    install_sidebar,
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
    "Ask me anything about FireMapSim - how a control works, where to find "
    "it, or what a setting means. I'll point to it on the page while I explain."
)


def clean_for_display(text: str) -> str:
    """Plain text for the sidebar bubble. The API already strips markdown;
    this guards against an older server."""
    return strip_markdown(text)


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

        # Registered before the first load and re-run on every reload, so a
        # navigation inside FireMapSim (e.g. login) doesn't end the session.
        install_sidebar(page, SIDEBAR_WIDTH, WELCOME_MESSAGE)

        print(f"Opening FireMapSim at {FIRESIM_BASE} ...")
        # No lat/lng/zoom seeded here — FireMapSim opens at its own default
        # view and the user moves the map themselves.
        page.goto(FIRESIM_BASE, wait_until="domcontentloaded", timeout=60000)
        # Wait for Mapbox canvas — networkidle can hang on tile streaming.
        try:
            page.wait_for_selector(".mapboxgl-canvas, .map-layer canvas", timeout=30000)
        except Exception:
            print("  !  Map canvas selector not found yet — continuing anyway.")
        print("Page loaded.\n")

        # Let the Vue app and Mapbox finish initializing.
        time.sleep(2)

        print("Ready. Click the orange button (bottom-right) to open the helper")
        print("and type a message. Close the browser window to end the session.\n")

        while not page.is_closed():
            try:
                user_msg = wait_for_user_message(page)
            except Exception:
                break  # page/browser was closed
            if user_msg is None:
                continue  # page reloaded mid-wait; sidebar is re-injected

            print(f"\nUser: {user_msg}")

            try:
                response = api_chat(user_msg)
            except Exception as exc:
                print(f"  x API error: {exc}")
                try:
                    append_agent_error(page, "Sorry, I ran into a problem reaching the assistant. Please try again.")
                except Exception:
                    pass  # page reloaded; the loop exits if it actually closed
                continue

            reply = response["reply"]
            narrate(reply)

            # Show the reply first: highlighting may have to scroll.
            try:
                append_agent_reply(page, clean_for_display(reply))
            except Exception:
                continue

            # Clear the previous highlight before applying the next one.
            highlight_off(page)

            # The server's highlight list decides; text matching is only a
            # fallback for an older server that doesn't send the field.
            step_key = pick_highlight(response.get("highlight"), reply)
            if step_key:
                highlight_on(page, STEP_SELECTORS[step_key], step_key)
            else:
                print("  (no highlight for this reply)")

        print("\nSession ended (browser closed).")
        try:
            browser.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
