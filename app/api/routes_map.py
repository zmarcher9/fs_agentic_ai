"""
POST /api/map/navigate

Thin HTTP entry point over the same BrowserSessionPool.navigate() that
the agent's navigate_map tool calls — one actuation path, two callers.

Auth: issued X-Session-Id (see app/core/session_tokens.py).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.browser.pool import MapNotReadyError, NoActiveSessionError, PoolExhaustedError, pool
from app.core.location_parser import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN
from app.core.map_bounds import MAX_ZOOM, MIN_ZOOM
from app.core.rate_limiter import RateLimitExceededError
from app.core.session_tokens import is_valid_session

router = APIRouter()


class NavigateMapRequest(BaseModel):
    lat: float = Field(..., ge=LAT_MIN, le=LAT_MAX)
    lon: float = Field(..., ge=LON_MIN, le=LON_MAX)
    zoom: Optional[int] = Field(default=None, ge=MIN_ZOOM, le=MAX_ZOOM)
    label: Optional[str] = None


class NavigateMapResponse(BaseModel):
    ok: bool
    lat: float
    lon: float
    zoom: int
    label: Optional[str]
    message: str


def get_session_id(x_session_id: Optional[str] = Header(default=None)) -> str:
    """
    Auth dependency — header must be a token this process issued
    (see app/core/session_tokens.py), not just any non-empty string.
    """
    if not x_session_id or not is_valid_session(x_session_id):
        raise HTTPException(status_code=401, detail="Missing or invalid X-Session-Id")
    return x_session_id


@router.post("/api/map/navigate", response_model=NavigateMapResponse)
async def navigate_map_route(
    body: NavigateMapRequest, session_id: str = Depends(get_session_id)
) -> NavigateMapResponse:
    try:
        result = await pool.navigate(
            session_id=session_id,
            lat=body.lat,
            lon=body.lon,
            zoom=body.zoom,
            label=body.label,
            source="http",
        )
    except NoActiveSessionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RateLimitExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except (PoolExhaustedError, MapNotReadyError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return NavigateMapResponse(**result)
