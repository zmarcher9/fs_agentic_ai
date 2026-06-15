"""
demo/run_demo.py

End-to-end scripted demo for the firesim-ai project.
Walks through the Canton, GA prescribed burn scenario:

    natural language input
        → geocoding + coordinate conversion
        → simulation config JSON
        → step-by-step UI narration

Run with:
    python demo/run_demo.py

Requires the FastAPI server to be running:
    python -m uvicorn api.main:app --reload --port 8000

Optional: also start the Playwright guide in a second terminal:
    python playwright/guide.py

Thread ID:
    This script and playwright/guide.py share an agent conversation via the
    FIRESIM_THREAD_ID environment variable. If it's not set, both scripts
    fall back to the same default thread ("canton-demo-default"), so by
    default they're already talking about the same configured scenario.

    To use a fresh thread for a one-off run, set FIRESIM_THREAD_ID before
    launching either script:

        export FIRESIM_THREAD_ID=canton-demo-20260615-130800   (bash)
        $env:FIRESIM_THREAD_ID = "canton-demo-20260615-130800" (PowerShell)

    Run this script first to configure the scenario, then run
    playwright/guide.py with the SAME FIRESIM_THREAD_ID (if you set one)
    to walk through the UI for that configured session.
"""

import json
import os
import time
import textwrap
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

API_URL = "http://localhost:8000/chat"

# Shared with playwright/guide.py via the FIRESIM_THREAD_ID env var, so both
# scripts talk to the same agent conversation. See module docstring above.
THREAD_ID = os.environ.get("FIRESIM_THREAD_ID", "canton-demo-default")

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
    # Preserve any JSON blocks; wrap everything else.
    in_json = False
    for line in reply.splitlines():
        stripped = line.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            in_json = True
        if in_json:
            print(f"    {line}")
            if stripped.endswith("}") or stripped.endswith("]"):
                in_json = False
        else:
            for wrapped in textwrap.wrap(line, width=TERM_WIDTH - 4) or [""]:
                print(f"    {wrapped}")


def chat(message: str, pause: float = 0.5) -> str:
    """
    POST to /chat, return the agent reply.
    Adds a small pause before each call so the demo doesn't feel rushed.
    """
    time.sleep(pause)
    try:
        resp = requests.post(
            API_URL,
            json={"message": message, "thread_id": THREAD_ID},
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["reply"]
    except requests.exceptions.ConnectionError:
        return (
            "[ERROR] Could not reach the firesim-ai API at localhost:8000.\n"
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


def extract_json_block(text: str) -> dict | None:
    """
    Pull the first JSON object out of a string (agent reply may embed config).
    Returns parsed dict or None.
    """
    try:
        start = text.index("{")
        end   = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Demo script
# ---------------------------------------------------------------------------

TURNS: list[tuple[str, str]] = [
    # (label, user message)

    (
        "1. Natural-language setup request",
        "I need to set up a prescribed burn simulation near Canton, GA. "
        "The burn area is about 500 acres and I want to run it for 3 hours."
    ),
    (
        "2. Ask for coordinate details",
        "What coordinates did you calculate for Canton, GA, and what "
        "projection will you use for the simulation grid?"
    ),
    (
        "3. Request the full configuration JSON",
        "Can you give me the complete simulation configuration JSON "
        "for this Canton burn, including cell resolution, grid size, "
        "wind parameters, and projection center?"
    ),
    (
        "4. Ask about wind conditions",
        "For a controlled burn in Cherokee County in spring, what wind speed "
        "and direction would be typical? Update the config if needed."
    ),
    (
        "5. UI step — Set Project Location",
        "Walk me through setting the project location in FireMapSim for "
        "the Canton coordinates."
    ),
    (
        "6. UI step — Cell resolution",
        "What cell resolution and grid dimension should I select in the "
        "Cell Resolution and Cell Space Dimension dropdowns?"
    ),
    (
        "7. UI step — Terrain and fuel data",
        "How do I load the terrain and fuel data for this Canton area "
        "once the grid boundary is set?"
    ),
    (
        "8. UI step — Ignition lines",
        "The prescribed burn will use two ignition teams working inward "
        "from the north and south edges. How do I draw those ignition lines?"
    ),
    (
        "9. UI step — Simulation parameters",
        "Where do I enter the simulation duration and wind settings in "
        "the FireMapSim interface?"
    ),
    (
        "10. UI step — Start simulation",
        "Everything looks good. How do I start the simulation run?"
    ),
    (
        "11. Wrap-up summary",
        "Give me a quick summary of everything we configured for the "
        "Canton, GA prescribed burn — coordinates, grid, wind, duration — "
        "so I can save it for the record."
    ),
]


def main() -> None:
    header("firesim-ai  ·  Canton, GA Prescribed Burn Demo")
    print(f"  Thread ID : {THREAD_ID}")
    print(f"  API URL   : {API_URL}")
    print(f"  Turns     : {len(TURNS)}")
    print()
    if "FIRESIM_THREAD_ID" not in os.environ:
        print("  (Using default shared thread. playwright/guide.py will use")
        print("   this same thread automatically if run without setting")
        print("   FIRESIM_THREAD_ID either.)")
        print()

    # Check the API is up before starting
    section("Health check")
    try:
        resp = requests.get("http://localhost:8000/health", timeout=5)
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

    config_json = None

    for label, msg in TURNS:
        section(label)
        reply = run_turn(msg, pause_after=2.0)

        # If this turn produced a JSON config, stash it for display later.
        if config_json is None:
            config_json = extract_json_block(reply)

    # ---------------------------------------------------------------------------
    # Final summary
    # ---------------------------------------------------------------------------
    header("Demo Complete")

    if config_json:
        section("Extracted simulation config")
        print(json.dumps(config_json, indent=2))
    else:
        print("  (No JSON config block detected in replies.)")

    divider("═")
    print()
    print("  Next steps:")
    print("  1. Open https://firesim.cs.gsu.edu/ in your browser.")
    print("  2. Run:  python playwright/guide.py")
    print(f"     (it will use the same thread: {THREAD_ID})")
    print("     The guide will highlight each field as the agent narrates.")
    print()
    divider("═")


if __name__ == "__main__":
    main()