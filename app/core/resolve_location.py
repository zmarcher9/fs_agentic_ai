"""
resolve_location — the single place that turns raw chat text into
either usable (lat, lon) or a typed, narratable outcome.

classify_location's ValueError (malformed / out-of-range coordinates)
is intentionally allowed to propagate: that's a hard usage error, same
family as navigate_map's bounds/zoom checks, and the agent prompt is
responsible for turning it into a short correction message.

not_found and ambiguous are NOT exceptions — they're expected, valid
outcomes of a place lookup, each with its own payload shape (candidates
for ambiguous), so they come back as a structured result instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from app.core.geocoder import GeocodeCandidate, geocode
from app.core.location_parser import classify_location

# If the top candidate's importance beats the runner-up by at least
# this much, treat it as confidently resolved instead of asking the
# user to disambiguate. Tunable — no principled "correct" value here,
# just a starting point for demo usage (e.g. distinguishes "Paris,
# France" from a minor "Paris, Texas" hamlet, while still flagging
# genuinely comparable places like "Athens, GA" vs "Athens, Greece").
AMBIGUITY_IMPORTANCE_GAP = 0.05

MAX_AMBIGUOUS_CANDIDATES = 3


@dataclass(frozen=True)
class ResolvedLocation:
    status: Literal["resolved", "ambiguous", "not_found"]
    lat: Optional[float] = None
    lon: Optional[float] = None
    label: Optional[str] = None
    query: Optional[str] = None
    candidates: tuple[GeocodeCandidate, ...] = field(default_factory=tuple)
    message: str = ""


async def resolve_location(text: str) -> ResolvedLocation:
    """
    classify -> (geocode if place) -> ResolvedLocation.

    Raises ValueError for malformed/out-of-range coordinate input
    (propagated straight from classify_location) — that's a usage
    error, not a "didn't find it" outcome.
    """
    parsed = classify_location(text)  # ValueError propagates on purpose

    if parsed.kind == "coordinates":
        return ResolvedLocation(
            status="resolved",
            lat=parsed.lat,
            lon=parsed.lon,
            label=None,
            query=parsed.raw,
            message=f"Using coordinates {parsed.lat}, {parsed.lon}",
        )

    query = parsed.place_query or parsed.raw
    candidates = await geocode(query)

    if not candidates:
        return ResolvedLocation(
            status="not_found",
            query=query,
            message="I couldn't find that place. Try a fuller name or lat/lon.",
        )

    if _top_is_confident(candidates):
        top = candidates[0]
        return ResolvedLocation(
            status="resolved",
            lat=top.lat,
            lon=top.lon,
            label=top.display_name,
            query=query,
            message=f"Resolved to {top.display_name}",
        )

    shortlist = tuple(candidates[:MAX_AMBIGUOUS_CANDIDATES])
    names = [c.display_name for c in shortlist]
    return ResolvedLocation(
        status="ambiguous",
        query=query,
        candidates=shortlist,
        message=f"That matched several places — did you mean {_format_choices(names)}?",
    )


def _top_is_confident(candidates: list[GeocodeCandidate]) -> bool:
    if len(candidates) < 2:
        return True
    return (candidates[0].importance - candidates[1].importance) >= AMBIGUITY_IMPORTANCE_GAP


def _format_choices(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} or {names[1]}"
    return ", ".join(names[:-1]) + f", or {names[-1]}"
