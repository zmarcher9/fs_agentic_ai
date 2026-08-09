"""Mapbox panning helpers for playwright/guide.py's visible page."""

import time

from playwright.sync_api import Page

from app.browser.map_control import PAN_MAP_JS


def firesim_url(base: str, lat: float, lng: float, zoom: int) -> str:
    """Build a FireMapSim URL whose query params seed the initial map center."""
    return f"{base}?lat={lat}&lng={lng}&zoom={zoom}"


# PAN_MAP_JS (Vue FireMap walk + .mapboxgl-map DOM fallback) is imported
# from app.browser.map_control — the same JS the agent's headless tab runs
# via pan_map(), so guide.py's visible page and the agent's tab move the
# map identically. It throws on failure rather than returning a status,
# and its arg order is [lng, lat, zoom, method] (Mapbox convention).


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
    Retries until the map finishes loading. Instant jump (cold-load
    positioning) — see pan_map_live() for the animated chat-driven pan.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            page.evaluate(PAN_MAP_JS, [lng, lat, zoom, "jumpTo"])
            print(f"  -> Map panned to ({lat}, {lng}) zoom={zoom}  [attempt {attempt}]")
            return
        except Exception as exc:
            print(f"  ... map not ready ({attempt}/{max_attempts}): {exc}")
            time.sleep(retry_delay)

    print("  !  Map pan failed after retries — user can pan manually.")


def pan_map_live(page: Page, lat: float, lng: float, zoom: int) -> None:
    """
    Animated pan (flyTo) used to keep guide.py's own visible page in sync
    with a resolved location from the agent's reply. The agent's
    navigate_map tool call already moved its own headless tab (a separate
    page instance against the same FIREMAP_URL) this is what makes the
    page move too.
    """
    try:
        page.evaluate(PAN_MAP_JS, [lng, lat, zoom, "flyTo"])
        print(f"  -> Sidebar page synced to agent's move: ({lat}, {lng}) zoom={zoom}")
    except Exception as exc:
        print(f"  !  Could not sync map pan: {exc}")
