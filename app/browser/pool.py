"""
BrowserSessionPool — session-keyed Playwright context pool.

Policy (per spec):
  Browser : one Chromium process per API worker, started in FastAPI lifespan
  Context : one context per active user session
  Page    : one FireMapSim page per context, reused across navigate calls
  Key     : session_id from auth (X-Session-Id for now; see routes_map.py)

Max contexts is a hard cap. Policy is REJECT (503), not LRU-evict.
Idle TTL: idle-checked lazily on next get_or_create.
Concurrency: one navigate at a time per context (per-entry asyncio.Lock).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.browser.map_control import pan_map
from app.core.audit_log import log_navigation
from app.core.location_parser import check_bounds
from app.core.map_bounds import validate_zoom
from app.core.rate_limiter import navigate_rate_limiter


class PoolExhaustedError(Exception):
    """Max contexts reached and no idle slot could be freed. -> 503."""


class NoActiveSessionError(Exception):
    """
    The session's browser/page was found but is dead (crashed or closed
    out from under us) and couldn't be recovered within this call.
    -> 404. The *next* call for the same session_id will auto-create a
    fresh context, since the dead entry is removed before raising.
    """


class MapNotReadyError(Exception):
    """The page loaded but the Vue FireMap / Mapbox instance wasn't
    found by pan_map (e.g. still loading). -> 503."""


@dataclass
class _SessionEntry:
    context: Any  # playwright.async_api.BrowserContext
    page: Any  # playwright.async_api.Page
    nav_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_used: float = field(default_factory=time.monotonic)

    def touch(self) -> None:
        self.last_used = time.monotonic()

    def idle_seconds(self) -> float:
        return time.monotonic() - self.last_used


class BrowserSessionPool:
    def __init__(
        self,
        max_contexts: int = 8,
        idle_ttl_seconds: float = 600.0,
        target_url: str = "http://localhost:5173",
    ):
        self.max_contexts = max_contexts
        self.idle_ttl_seconds = idle_ttl_seconds
        self.target_url = target_url

        self._browser: Any = None
        self._playwright: Any = None
        self._entries: dict[str, _SessionEntry] = {}
        self._pool_lock = asyncio.Lock()  # guards _entries structure (create/evict/close)

    # ---- lifecycle (call from FastAPI lifespan) ---------------------------

    async def start(self, browser: Optional[Any] = None) -> None:
        """
        Launch the shared Chromium process. Pass `browser` to inject an
        already-launched (or fake, for tests) browser instead of
        launching a real one.
        """
        if browser is not None:
            self._browser = browser
            return
        from playwright.async_api import async_playwright  # lazy import

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)

    async def stop(self) -> None:
        """Close all contexts, then the browser. Call from lifespan shutdown."""
        async with self._pool_lock:
            for entry in list(self._entries.values()):
                await entry.context.close()
            self._entries.clear()
        if self._browser is not None:
            await self._browser.close()
        if self._playwright is not None:
            await self._playwright.stop()

    # ---- core pool logic ----------------------------------------------------

    async def get_or_create(self, session_id: str) -> _SessionEntry:
        async with self._pool_lock:
            entry = self._entries.get(session_id)
            if entry is not None:
                if entry.idle_seconds() > self.idle_ttl_seconds:
                    await self._close_entry_locked(session_id, entry)
                else:
                    entry.touch()
                    return entry

            self._evict_idle_locked()

            if len(self._entries) >= self.max_contexts:
                raise PoolExhaustedError(
                    f"Browser context pool full ({self.max_contexts} active sessions)"
                )

            context = await self._browser.new_context()
            page = await context.new_page()
            await page.goto(self.target_url)
            new_entry = _SessionEntry(context=context, page=page)
            self._entries[session_id] = new_entry
            return new_entry

    def _evict_idle_locked(self) -> None:
        """Drop entries past idle_ttl_seconds that aren't mid-navigate.
        Must be called while holding self._pool_lock."""
        stale = [
            sid
            for sid, e in self._entries.items()
            if e.idle_seconds() > self.idle_ttl_seconds and not e.nav_lock.locked()
        ]
        for sid in stale:
            entry = self._entries.pop(sid)
            asyncio.create_task(entry.context.close())

    async def _close_entry_locked(self, session_id: str, entry: _SessionEntry) -> None:
        self._entries.pop(session_id, None)
        await entry.context.close()

    async def drop_session(self, session_id: str) -> None:
        """Explicitly tear down a session's context (e.g. on crash detection)."""
        async with self._pool_lock:
            entry = self._entries.pop(session_id, None)
        if entry is not None:
            await entry.context.close()

    # ---- the one shared actuation path (agent tool + HTTP route both call this) --

    async def navigate(
        self,
        session_id: str,
        lat: float,
        lon: float,
        zoom: Optional[int] = None,
        label: Optional[str] = None,
        method: str = "flyTo",
        source: str = "unknown",
    ) -> dict:
        """
        `source` is "tool" (agent-initiated) or "http" (direct API call)
        — purely for the audit log, doesn't change behavior.
        """
        try:
            if not session_id:
                raise NoActiveSessionError("No session_id provided")

            # Rate limit before doing any real work — a caller spamming
            # invalid input shouldn't get a free pass on validation cost.
            await navigate_rate_limiter.enforce(session_id, "navigate")

            # Re-run the same gate as everywhere else — never trust the caller.
            check_bounds(lat, lon, raw=f"{lat}, {lon}")
            resolved_zoom = validate_zoom(zoom)

            entry = await self.get_or_create(session_id)

            async with entry.nav_lock:  # serialize navigates within this session only
                try:
                    if entry.page.is_closed():
                        await self.drop_session(session_id)
                        raise NoActiveSessionError(
                            f"Browser page for session {session_id!r} is no longer open"
                        )
                    await pan_map(
                        entry.page, lat=lat, lon=lon, zoom=resolved_zoom, method=method
                    )
                except NoActiveSessionError:
                    raise
                except Exception as exc:  # page.evaluate found no map instance, crashed, etc.
                    raise MapNotReadyError(str(exc)) from exc

            message = f"Moved map to {label}" if label else f"Moved map to {lat}, {lon}"
            result = {
                "ok": True,
                "lat": lat,
                "lon": lon,
                "zoom": resolved_zoom,
                "label": label,
                "message": message,
            }
            log_navigation(
                session_id, lat, lon, resolved_zoom, label, ok=True, source=source
            )
            return result
        except Exception as exc:
            log_navigation(
                session_id, lat, lon, zoom, label, ok=False, source=source, error=str(exc)
            )
            raise


# Module-level singleton — imported by both the agent tool and the HTTP
# route so they share exactly one pool / one actuation path. Started and
# stopped from the FastAPI lifespan (see app/api/routes_map.py).
pool = BrowserSessionPool()
