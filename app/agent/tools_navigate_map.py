"""
navigate_map tool — LangGraph-facing entry to BrowserSessionPool.navigate.

Zoom policy: REJECT out-of-range/non-int zoom (raise ValueError), don't clamp.
"""

import json
from typing import Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.agent.navigation_grants import navigation_grants
from app.browser.pool import MapNotReadyError, NoActiveSessionError, PoolExhaustedError, pool
from app.core.location_parser import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN
from app.core.map_bounds import MAX_ZOOM, MIN_ZOOM
from app.core.rate_limiter import RateLimitExceededError


class NavigateMapInput(BaseModel):
    lat: float = Field(..., ge=LAT_MIN, le=LAT_MAX)
    lon: float = Field(..., ge=LON_MIN, le=LON_MAX)
    zoom: Optional[int] = Field(
        default=None,
        ge=MIN_ZOOM,
        le=MAX_ZOOM,
        description=f"Map zoom level, {MIN_ZOOM}-{MAX_ZOOM}. Omit for default.",
    )
    label: Optional[str] = Field(
        default=None,
        description="Human-readable place name if known (e.g. from resolve_location). "
        "Leave unset for raw coordinate input.",
    )


def _session_id_from_config(config: Optional[RunnableConfig]) -> str:
    """
    LangGraph puts the conversation's thread id at
    config["configurable"]["thread_id"]. That value must be the same
    server-issued session token used as X-Session-Id.
    """
    thread_id = (config or {}).get("configurable", {}).get("thread_id")
    if not thread_id:
        raise ValueError(
            "No thread_id in RunnableConfig — navigate_map needs a session to "
            "know which browser context to drive."
        )
    return thread_id


@tool("navigate_map", args_schema=NavigateMapInput)
async def navigate_map(
    lat: float,
    lon: float,
    zoom: Optional[int] = None,
    label: Optional[str] = None,  # unused: accepted for schema/prompt parity only,
    # model-supplied labels are untrusted — grant.label is used instead below.
    config: RunnableConfig = None,
) -> str:
    """
    Move the map to the given latitude/longitude and return a structured
    result for the agent to narrate back to the user.

    Call this only once lat/lon are known — either the user gave
    coordinates directly (via classify_location) or a place description
    was already geocoded (via resolve_location). Never call this with an
    un-geocoded place name in lat/lon.
    """
    session_id = _session_id_from_config(config)

    try:
        grant = navigation_grants.consume(session_id, lat, lon)
    except ValueError as exc:
        # No grant, or one that doesn't match these coordinates (e.g.
        # navigate_map called without a preceding resolve_location, or a
        # stale grant already consumed by an earlier call). Same "return a
        # structured failure instead of raising" reasoning as below — kept
        # in its own except so a real ValueError from pool.navigate() isn't
        # silently swallowed by this same branch.
        return json.dumps({"ok": False, "error": str(exc), "lat": lat, "lon": lon, "label": None})

    try:
        result = await pool.navigate(
            session_id=session_id,
            lat=lat,
            lon=lon,
            zoom=zoom,
            # The external label comes from the sanitized resolver result, not
            # from model-authored tool arguments.
            label=grant.label,
            requested_text=grant.raw_query,
            source="tool",
        )
    except (
        NoActiveSessionError,
        PoolExhaustedError,
        MapNotReadyError,
        RateLimitExceededError,
    ) as exc:
        # Return a structured failure instead of raising: the browser-side
        # actuation failing (map not loaded, pool busy, etc.) is a transient
        # operational condition, not a reason to fail the whole chat turn.
        # The agent narrates this in plain language, same as resolve_location's
        # ambiguous/not_found statuses.
        return json.dumps(
            {
                "ok": False,
                "error": str(exc),
                "lat": lat,
                "lon": lon,
                "label": grant.label,
            }
        )

    return json.dumps(result)
