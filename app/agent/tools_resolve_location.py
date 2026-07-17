"""
resolve_location tool — LangGraph-facing entry to app.core.resolve_location.

See app/core/resolve_location.py for why not_found/ambiguous are
returned as structured results, not raised, while malformed/out-of-range
coordinate text still raises (same family as navigate_map's bounds/zoom
checks — a real usage error, not a lookup miss).

Prompt note: call navigate_map with the returned lat/lon (+label) only
when status == "resolved". On "ambiguous", ask the user which candidate
they meant — don't guess. On "not_found", ask for a fuller name or
coordinates. Never fall back to a default location after a miss.
"""

import json

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.agent.navigation_grants import navigation_grants
from app.core.resolve_location import resolve_location


class ResolveLocationInput(BaseModel):
    text: str = Field(..., description="Raw place description or lat/lon text from the user.")


@tool("resolve_location", args_schema=ResolveLocationInput)
async def resolve_location_tool(
    text: str, config: RunnableConfig = None
) -> str:
    """
    Classify and, if needed, geocode raw location text.

    Returns JSON: {"ok", "status": "resolved"|"ambiguous"|"not_found",
    "lat", "lon", "label", "query", "candidates": [...], "message"}.

    Call navigate_map only when status == "resolved". On "ambiguous",
    ask the user which candidate they meant. On "not_found", ask for a
    fuller name or coordinates. Never invent lat/lon from a miss.

    Raises on malformed/out-of-range coordinate text (e.g. "95, -84")
    — that's a usage error, not a lookup miss.
    """
    result = await resolve_location(text)
    thread_id = (config or {}).get("configurable", {}).get("thread_id")
    if (
        result.status == "resolved"
        and result.lat is not None
        and result.lon is not None
        and thread_id
    ):
        navigation_grants.issue(
            thread_id,
            result.lat,
            result.lon,
            result.label,
            raw_query=result.query or text,
        )

    return json.dumps(
        {
            "ok": result.status == "resolved",
            "status": result.status,
            "lat": result.lat,
            "lon": result.lon,
            "label": result.label,
            "query": result.query,
            "candidates": [
                {"lat": c.lat, "lon": c.lon, "display_name": c.display_name}
                for c in result.candidates
            ],
            "message": result.message,
        }
    )
