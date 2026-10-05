"""
demo/run_demo.py

End-to-end scripted demo for the firesim-ai Q&A helper.
Asks the kinds of questions a first-time FireMapSim user would ask while
setting up a prescribed burn:

    "how do I use this control?"   → plain-English UI steps
    "what does this setting mean?" → background explanation
    "just do it for me"            → declines, says what to click instead

The helper never moves the map or fills in fields — the user does.

Run with:
    python demo/run_demo.py

Requires the FastAPI server to be running:
    python -m uvicorn api.main:app --reload --port 8000

Optional: also start the Playwright guide in a second terminal:
    python playwright/guide.py

Thread / session ID:
    Chat requires a server-issued X-Session-Id from POST /api/session.
    This script issues one on first chat (or reuses FIRESIM_SESSION_ID).
    Share that value with playwright/guide.py:

        $env:FIRESIM_SESSION_ID = "<token from demo>"

"""

import os
import time
import textwrap
import requests

from app.config import get_settings

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_settings = get_settings()
API_BASE_URL = _settings.api_base_url.rstrip("/")
FIREMAP_URL = _settings.firemap_url
API_URL = f"{API_BASE_URL}/chat"
SESSION_URL = f"{API_BASE_URL}/api/session"

# Prefer a server-issued token from a prior /api/session call (share across
# demo + guide via FIRESIM_SESSION_ID). Otherwise a fresh token is issued
# on first chat().
_SESSION_ID = os.environ.get("FIRESIM_SESSION_ID")

# Width for terminal output formatting
TERM_WIDTH = 72


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def divider(char: str = "─", width: int = TERM_WIDTH) -> None:
    print(char * width)


def header(title: str) -> None:
    divider("═")
    print(f"  {title}")
    divider("═")
    print()


def section(label: str) -> None:
    print()
    divider()
    print(f"  {label}")
    divider()


def print_user(msg: str) -> None:
    print(f"\n👤  USER:\n")
    for line in textwrap.wrap(msg, width=TERM_WIDTH - 4):
        print(f"    {line}")


def print_agent(reply: str) -> None:
    print(f"\n🤖  AGENT:\n")
    # The agent narrates everything in plain English (system prompt forbids
    # raw JSON in replies — see FIRESIM_SYSTEM_PROMPT), so replies are just
    # wrapped text, no code-block preservation needed.
    for line in reply.splitlines():
        for wrapped in textwrap.wrap(line, width=TERM_WIDTH - 4) or [""]:
            print(f"    {wrapped}")


def get_session_id() -> str:
    global _SESSION_ID
    if _SESSION_ID:
        return _SESSION_ID
    resp = requests.post(SESSION_URL, timeout=30)
    resp.raise_for_status()
    _SESSION_ID = resp.json()["session_id"]
    print(f"  (Issued session_id={_SESSION_ID[:12]}… — set FIRESIM_SESSION_ID to reuse)")
    return _SESSION_ID


def chat(message: str, pause: float = 0.5) -> str:
    """
    POST to /chat, return the agent reply.
    Adds a small pause before each call so the demo doesn't feel rushed.
    """
    time.sleep(pause)
    try:
        session_id = get_session_id()
        resp = requests.post(
            API_URL,
            json={"message": message},
            headers={"X-Session-Id": session_id},
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["reply"]
    except requests.exceptions.ConnectionError:
        return (
            f"[ERROR] Could not reach the firesim-ai API at {API_BASE_URL}.\n"
            "Make sure the server is running:\n"
            "    python -m uvicorn api.main:app --reload --port 8000"
        )
    except Exception as exc:
        return f"[ERROR] {exc}"


def run_turn(user_msg: str, pause_after: float = 1.5) -> str:
    """Run one conversation turn: print user message, get reply, print reply."""
    print_user(user_msg)
    reply = chat(user_msg)
    print_agent(reply)
    time.sleep(pause_after)
    return reply


# ---------------------------------------------------------------------------
# Demo script
# ---------------------------------------------------------------------------

TURNS: list[tuple[str, str]] = [
    # (label, user message)

    (
        "1. Getting oriented",
        "I'm new to FireMapSim. What are the main steps to set up and run "
        "a prescribed burn simulation?"
    ),
    (
        "2. UI how-to — project location",
        "How do I set the project location to my farm near Canton, GA?"
    ),
    (
        "3. Asking the helper to act (it should decline)",
        "Can you just move the map to Canton, GA for me?"
    ),
    (
        "4. Background — grid settings",
        "What's the difference between Cell Resolution and Cell Space "
        "Dimension, and how do they affect the size of the area?"
    ),
    (
        "5. UI how-to — terrain and fuel",
        "How do I see the fuel and slope for my area? Do I have to?"
    ),
    (
        "6. UI how-to — ignition lines",
        "Our burn will use two ignition teams working inward from the north "
        "and south edges. How do I draw those ignition lines?"
    ),
    (
        "7. UI how-to — wind",
        "Where do I enter wind speed and direction? Which way is 90 degrees?"
    ),
    (
        "8. Asking the helper to fill fields (it should decline)",
        "Set the wind to 15 km/h from the southwest and the duration to 3 hours."
    ),
    (
        "9. Background — fuel breaks",
        "What is a fuel break, and how do I add one?"
    ),
    (
        "10. UI how-to — run and review",
        "How do I start the simulation and then watch how the fire spread?"
    ),
]


def main() -> None:
    header("firesim-ai  ·  FireMapSim Q&A Helper Demo")
    session_id = get_session_id()
    print(f"  Session ID: {session_id[:16]}…")
    print(f"  API URL   : {API_URL}")
    print(f"  Turns     : {len(TURNS)}")
    print()
    print("  Share with playwright/guide.py via:")
    print(f"    $env:FIRESIM_SESSION_ID = '{session_id}'")
    print()

    # Check the API is up before starting
    section("Health check")
    try:
        resp = requests.get(f"{API_BASE_URL}/health", timeout=5)
        resp.raise_for_status()
        status = resp.json()
        print(f"  ✓  API is up — {status}")
    except Exception as exc:
        print(f"  ✗  API not reachable: {exc}")
        print("\n  Start the server first:")
        print("      python -m uvicorn api.main:app --reload --port 8000")
        return

    print()
    input("  Press ENTER to begin the demo …")
    print()

    for label, msg in TURNS:
        section(label)
        run_turn(msg, pause_after=2.0)

    # ---------------------------------------------------------------------------
    # Final summary
    # ---------------------------------------------------------------------------
    header("Demo Complete")
    divider("═")
    print()
    print("  Next steps:")
    print(f"  1. Open {FIREMAP_URL} in your browser.")
    print("  2. Set the same session for the guide:")
    print(f"       $env:FIRESIM_SESSION_ID = '{session_id}'")
    print("  3. Run:  python playwright/guide.py")
    print()
    divider("═")


if __name__ == "__main__":
    main()