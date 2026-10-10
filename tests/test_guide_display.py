"""Tests for reply cleanup: app.core.text_format.strip_markdown (server) and
playwright/guide.py's clean_for_display (guide)."""

import importlib.util
from pathlib import Path

import pytest

from app.core.text_format import strip_markdown

# `import playwright.guide` would hit the real playwright package, so load
# the script by path.
_GUIDE_PATH = Path(__file__).resolve().parent.parent / "playwright" / "guide.py"
_spec = importlib.util.spec_from_file_location("firesim_guide_script", _GUIDE_PATH)
guide = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guide)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Click **Start Simulation Run**.", "Click Start Simulation Run."),
        ("## Steps\n1. Click *Show Fuel*.", "Steps\n1. Click Show Fuel."),
        ("See [FireMapSim](https://firesim.cs.gsu.edu/) for more.", "See FireMapSim for more."),
        ("30 m * 50 cells * 1 = 1,500 m", "30 m * 50 cells * 1 = 1,500 m"),
        # Fence markers go, the content stays (it's usually the steps).
        ('Before\n```json\n{"step": "x"}\n```\nAfter', 'Before\n{"step": "x"}\nAfter'),
        # A one-line fence keeps its text (council review: it used to vanish).
        ("Then ```Click Start Simulation Run.```", "Then Click Start Simulation Run."),
        # The paragraph break before a heading survives.
        ("Intro\n\n## Heading\nText", "Intro\n\nHeading\nText"),
        ("Use the `Wind Speed` box.", "Use the Wind Speed box."),
        ("Path C:\\fires\\new is fine", "Path C:\\fires\\new is fine"),
        ("Files C:\\data\\*.json and a*b*c stay", "Files C:\\data\\*.json and a*b*c stay"),
    ],
)
def test_reply_cleanup(raw, expected):
    assert strip_markdown(raw) == expected
    assert guide.clean_for_display(raw) == expected


def test_strip_markdown_is_fast_on_hostile_input():
    # Regression (council review): the old italic regex was quadratic —
    # 40k chars of " *a*b" took ~2 s on the event loop.
    import time

    text = " *a*b" * 8000
    start = time.perf_counter()
    strip_markdown(text)
    assert time.perf_counter() - start < 0.2
