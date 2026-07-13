"""
Nominatim geocoding client — place text -> candidate coordinates.

Respects Nominatim's usage policy: max 1 request/sec, descriptive
User-Agent required. Caches resolved queries in-memory to cut both
latency and outbound call volume as usage grows.

NOT exercised against the live Nominatim API in this build — that
domain isn't reachable from this sandbox's network allowlist. Tests
mock the HTTP transport instead. Nominatim's JSON response shape has
been stable for a long time, but it's still an external dependency you
don't control — worth one manual smoke-test call before relying on
this against real traffic.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.sanitize import sanitize_label

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# https://operations.osmfoundation.org/policies/nominatim/ caps
# unauthenticated use at 1 request/second.
MIN_REQUEST_INTERVAL_SECONDS = 1.0

# TODO: put a real contact here per Nominatim's usage policy (they want
# an identifiable User-Agent/Referer so they can reach out if a client
# misbehaves — an anonymous UA risks getting rate-limited or blocked).
USER_AGENT = "FireSim-AI/1.0 (contact: set-a-real-contact-here)"

_CACHE_MAX_ENTRIES = 500


@dataclass(frozen=True)
class GeocodeCandidate:
    lat: float
    lon: float
    display_name: str
    importance: float = 0.0


class _RateLimiter:
    """Serializes calls to at most one per `min_interval` seconds,
    process-wide, per Nominatim's usage policy."""

    def __init__(self, min_interval: float = MIN_REQUEST_INTERVAL_SECONDS):
        self.min_interval = min_interval
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def wait(self) -> None:
        async with self._lock:
            elapsed = time.monotonic() - self._last_call
            if elapsed < self.min_interval:
                await asyncio.sleep(self.min_interval - elapsed)
            self._last_call = time.monotonic()


_rate_limiter = _RateLimiter()
_cache: dict[str, list[GeocodeCandidate]] = {}


async def geocode(
    query: str,
    limit: int = 5,
    client: Optional[httpx.AsyncClient] = None,
) -> list[GeocodeCandidate]:
    """
    Look up `query` against Nominatim. Returns candidates in Nominatim's
    own relevance order (best first). Empty list means no results —
    never a partial or guessed result.

    Pass `client` to reuse a connection pool (e.g. one owned by the
    FastAPI app) or to inject a fake transport in tests.
    """
    cache_key = query.strip().lower()
    if cache_key in _cache:
        return _cache[cache_key]

    await _rate_limiter.wait()

    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=10.0)
    try:
        resp = await http_client.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": limit},
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        raw = resp.json()
    finally:
        if owns_client:
            await http_client.aclose()

    candidates = [
        GeocodeCandidate(
            lat=float(item["lat"]),
            lon=float(item["lon"]),
            display_name=sanitize_label(item.get("display_name", query)) or query,
            importance=float(item.get("importance", 0.0)),
        )
        for item in raw
    ]

    if len(_cache) >= _CACHE_MAX_ENTRIES:
        _cache.pop(next(iter(_cache)))  # crude FIFO eviction, fine at demo scale
    _cache[cache_key] = candidates

    return candidates


def clear_cache() -> None:
    """Mainly for tests — clears the module-level geocode cache."""
    _cache.clear()
