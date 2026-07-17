"""One async geocoding path with provider selection and bounded TTL caching."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import Settings, get_settings
from app.core.sanitize import sanitize_label

MIN_REQUEST_INTERVAL_SECONDS = 1.0
MAPBOX_URL = "https://api.mapbox.com/search/geocode/v6/forward"


@dataclass(frozen=True)
class GeocodeCandidate:
    lat: float
    lon: float
    display_name: str
    importance: float = 0.0


class _RateLimiter:
    """Serialize public Nominatim calls to its one-request/second policy."""

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


@dataclass
class _CacheEntry:
    expires_at: float
    candidates: list[GeocodeCandidate]


_cache: OrderedDict[str, _CacheEntry] = OrderedDict()
_cache_lock = asyncio.Lock()
_inflight: dict[str, asyncio.Task[list[GeocodeCandidate]]] = {}
_shared_client: httpx.AsyncClient | None = None


async def start_geocoder(settings: Settings | None = None) -> None:
    """Create the process-wide HTTP connection pool during API startup."""
    global _shared_client
    if _shared_client is None:
        config = settings or get_settings()
        _shared_client = httpx.AsyncClient(timeout=config.geocoder_timeout_seconds)


async def stop_geocoder() -> None:
    """Close the process-wide HTTP connection pool."""
    global _shared_client
    if _shared_client is not None:
        await _shared_client.aclose()
        _shared_client = None


async def geocode(
    query: str,
    limit: int = 5,
    client: Optional[httpx.AsyncClient] = None,
    settings: Settings | None = None,
) -> list[GeocodeCandidate]:
    """Resolve a place through the configured provider without blocking the event loop."""
    config = settings or get_settings()
    normalized = query.strip()
    if not normalized:
        return []
    if limit < 1:
        raise ValueError("geocode limit must be at least 1")

    cache_key = f"{config.geocoder_provider}:{limit}:{normalized.casefold()}"
    cached = await _cache_get(cache_key)
    if cached is not None:
        return cached

    async with _cache_lock:
        task = _inflight.get(cache_key)
        if task is None:
            task = asyncio.create_task(
                _fetch_geocode(normalized, limit, client=client, settings=config)
            )
            _inflight[cache_key] = task

    try:
        candidates = await task
    finally:
        async with _cache_lock:
            if _inflight.get(cache_key) is task:
                _inflight.pop(cache_key, None)

    await _cache_put(cache_key, candidates, config)
    return list(candidates)


async def _fetch_geocode(
    query: str,
    limit: int,
    *,
    client: httpx.AsyncClient | None,
    settings: Settings,
) -> list[GeocodeCandidate]:
    http_client = client or _shared_client
    owns_client = http_client is None
    if http_client is None:
        http_client = httpx.AsyncClient(timeout=settings.geocoder_timeout_seconds)
    try:
        if settings.geocoder_provider == "mapbox":
            return await _fetch_mapbox(query, limit, http_client, settings)
        return await _fetch_nominatim(query, limit, http_client, settings)
    finally:
        if owns_client:
            await http_client.aclose()


async def _fetch_nominatim(
    query: str,
    limit: int,
    client: httpx.AsyncClient,
    settings: Settings,
) -> list[GeocodeCandidate]:
    await _rate_limiter.wait()
    response = await client.get(
        settings.nominatim_url,
        params={"q": query, "format": "json", "limit": limit},
        headers={"User-Agent": settings.nominatim_user_agent},
    )
    response.raise_for_status()
    return [
        GeocodeCandidate(
            lat=float(item["lat"]),
            lon=float(item["lon"]),
            display_name=sanitize_label(item.get("display_name", query)) or query,
            importance=float(item.get("importance", 0.0)),
        )
        for item in response.json()
    ]


async def _fetch_mapbox(
    query: str,
    limit: int,
    client: httpx.AsyncClient,
    settings: Settings,
) -> list[GeocodeCandidate]:
    if not settings.mapbox_access_token:
        raise ValueError("MAPBOX_ACCESS_TOKEN is required for Mapbox geocoding")
    response = await client.get(
        MAPBOX_URL,
        params={
            "q": query,
            "limit": limit,
            "access_token": settings.mapbox_access_token,
            "permanent": str(settings.mapbox_permanent).lower(),
        },
    )
    response.raise_for_status()
    candidates: list[GeocodeCandidate] = []
    for index, feature in enumerate(response.json().get("features", [])):
        properties = feature.get("properties") or {}
        coordinates = (feature.get("geometry") or {}).get("coordinates") or []
        if len(coordinates) < 2:
            continue
        name = properties.get("name_preferred") or properties.get("name")
        place_formatted = properties.get("place_formatted")
        label = properties.get("full_address")
        if not label and name and place_formatted:
            label = f"{name}, {place_formatted}"
        label = label or name or feature.get("place_name") or query
        # V5 responses expose relevance. V6 may omit a numeric score, so retain
        # provider order with a small descending score for ambiguity handling.
        importance = float(feature.get("relevance", max(0.0, 1.0 - index * 0.01)))
        candidates.append(
            GeocodeCandidate(
                lat=float(coordinates[1]),
                lon=float(coordinates[0]),
                display_name=sanitize_label(label) or query,
                importance=importance,
            )
        )
    return candidates


async def _cache_get(key: str) -> list[GeocodeCandidate] | None:
    async with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        if entry.expires_at <= time.monotonic():
            _cache.pop(key, None)
            return None
        _cache.move_to_end(key)
        return list(entry.candidates)


async def _cache_put(
    key: str, candidates: list[GeocodeCandidate], settings: Settings
) -> None:
    if settings.geocoder_cache_max_entries == 0 or settings.geocoder_cache_ttl_seconds == 0:
        return
    async with _cache_lock:
        _cache[key] = _CacheEntry(
            expires_at=time.monotonic() + settings.geocoder_cache_ttl_seconds,
            candidates=list(candidates),
        )
        _cache.move_to_end(key)
        while len(_cache) > settings.geocoder_cache_max_entries:
            _cache.popitem(last=False)


def clear_cache() -> None:
    """Clear process-local geocoder state (primarily tests)."""
    _cache.clear()
    _inflight.clear()
