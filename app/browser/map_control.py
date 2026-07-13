"""
Shared map-actuation JS, used by BrowserSessionPool (and eventually
playwright/guide.py) so there's exactly one place that knows how to
reach into the page and move the map.

JS body is adapted from playwright/guide.py pan_map_to_project:
  - Vue FireMap walk via #app.__vue__ + $children
  - DOM Mapbox fallback on .mapboxgl-map
  - Updates FireMap.cur_lat / cur_long / coordinates / zoom
  - Calls map[method]({ center: [lng, lat], zoom, essential: true })

Arg order to evaluate is [lng, lat, zoom, method] (Mapbox convention).
method="flyTo" for chat nav; method="jumpTo" for guide / cold load.
"""

from __future__ import annotations

from typing import Any, Literal

# Reconciled with playwright/guide.py PAN_MAP_JS (FireMap Vue walk +
# .mapboxgl-map DOM fallback). Throws on failure so callers can map to
# MapNotReadyError. Supports flyTo | jumpTo via `method`.
_PAN_MAP_JS = """
([lng, lat, zoom, method]) => {
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
        throw new Error('No Vue FireMap / Mapbox instance found on page');
    }
    if (typeof map[method] !== 'function') {
        throw new Error('Map method not available: ' + method);
    }

    if (fireMap) {
        fireMap.cur_lat = lat;
        fireMap.cur_long = lng;
        fireMap.coordinates = [lng, lat];
        fireMap.zoom = zoom;
    }
    // Mapbox GL uses [longitude, latitude] order.
    map[method]({ center: [lng, lat], zoom: zoom, essential: true });
    window.dispatchEvent(new Event('resize'));
    return true;
}
"""


async def pan_map(
    page: Any,
    lat: float,
    lon: float,
    zoom: int,
    method: Literal["flyTo", "jumpTo"] = "flyTo",
) -> None:
    """
    Move the map via the page's own Mapbox/FireMap JS API.

    No selector clicking, ever — this only calls page.evaluate with a
    function reference (Mapbox's [lng, lat] argument order, not [lat, lng]).

    method="flyTo"  -> chat-driven navigation (animated, visible motion)
    method="jumpTo" -> guide.py / initial load (instant, no animation)
    """
    await page.evaluate(_PAN_MAP_JS, [lon, lat, zoom, method])
