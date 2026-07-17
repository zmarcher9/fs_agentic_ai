"""One-use authorization binding resolved locations to agent map moves."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class NavigationGrant:
    lat: float
    lon: float
    label: Optional[str]
    raw_query: Optional[str] = None


class NavigationGrantStore:
    """Process-local grants; browser sessions are process-local by design."""

    def __init__(self) -> None:
        self._grants: dict[str, NavigationGrant] = {}

    def issue(
        self,
        session_id: str,
        lat: float,
        lon: float,
        label: Optional[str],
        raw_query: Optional[str] = None,
    ) -> None:
        self._grants[session_id] = NavigationGrant(
            lat=lat, lon=lon, label=label, raw_query=raw_query
        )

    def consume(self, session_id: str, lat: float, lon: float) -> NavigationGrant:
        grant = self._grants.pop(session_id, None)
        if grant is None:
            raise ValueError(
                "navigate_map requires a successful resolve_location call in this session"
            )
        if abs(grant.lat - lat) > 1e-7 or abs(grant.lon - lon) > 1e-7:
            raise ValueError(
                "navigate_map coordinates do not match the resolved location"
            )
        return grant

    def clear(self) -> None:
        self._grants.clear()


navigation_grants = NavigationGrantStore()
