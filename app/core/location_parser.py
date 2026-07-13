"""
Location text classification for chat-driven map navigation.

Classifies raw chat input as either explicit coordinates or a free-text
place description. No network calls, no map/agent interaction — that
happens downstream in the resolve/navigate tool.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass(frozen=True)
class ParsedLocation:
    kind: Literal["coordinates", "place"]
    raw: str
    lat: Optional[float] = None          # set only for coordinates
    lon: Optional[float] = None          # set only for coordinates
    place_query: Optional[str] = None    # set only for place


LAT_MIN, LAT_MAX = -90.0, 90.0
LON_MIN, LON_MAX = -180.0, 180.0

_NUM = r"-?\d{1,3}(?:\.\d+)?"

# "lat: 34.2368 lon: -84.4908"  /  "Latitude=34.2368, Longitude=-84.4908"
_LABELED_PATTERN = re.compile(
    rf"^lat(?:itude)?\s*[:=]?\s*(?P<lat>{_NUM})\s*[,;]?\s*"
    rf"lon(?:gitude)?\s*[:=]?\s*(?P<lon>{_NUM})$",
    re.IGNORECASE,
)

# "34.2368, -84.4908"  /  "34.2368 -84.4908"  /  "34.2368,-84.4908"
_PLAIN_PAIR_PATTERN = re.compile(rf"^(?P<lat>{_NUM})\s*[,\s]\s*(?P<lon>{_NUM})$")

# "34.2368 N, 84.4908 W"  /  "34.2368N 84.4908W"
_DECIMAL_HEM_PATTERN = re.compile(r"(?P<val>\d{1,3}(?:\.\d+)?)\s*°?\s*(?P<hem>[NSEWnsew])")

# "34°14'12.5"N 84°29'26.7"W"  and  "34d14m12.5sN 84d29m26.7sW" style variants.
# Hemisphere letter is mandatory — this is what distinguishes a DMS token
# from a bare number, so it's what keeps this pattern from firing on
# ordinary text.
_DMS_TOKEN_PATTERN = re.compile(
    r"(?P<deg>\d{1,3}(?:\.\d+)?)\s*(?:°|d)\s*"
    r"(?:(?P<min>\d{1,2}(?:\.\d+)?)\s*(?:'|′|m)\s*)?"
    r'(?:(?P<sec>\d{1,2}(?:\.\d+)?)\s*(?:"|″|s)\s*)?'
    r"(?P<hem>[NSEWnsew])",
    re.IGNORECASE,
)

# After every coordinate pattern fails: if the string is made up only of
# digits/punctuation/hemisphere letters (no place-name text), it's a
# malformed coordinate attempt, not a place — hard fail instead of
# silently shipping it off to the geocoder.
_LOOKS_NUMERIC_PATTERN = re.compile(r"^[\d\s,.\-+°'\"′″NSEWnsew]+$")


def _dms_to_decimal(deg: str, minute: Optional[str], sec: Optional[str], hem: str) -> float:
    value = float(deg)
    if minute:
        value += float(minute) / 60.0
    if sec:
        value += float(sec) / 3600.0
    if hem.upper() in ("S", "W"):
        value = -value
    return value


def _order_by_hemisphere(
    vals: list[float], hems: list[str]
) -> Optional[tuple[float, float]]:
    """
    Map two signed values + hemisphere letters to (lat, lon), regardless
    of input order. Returns None (not an error) when the hemisphere
    letters don't cover one N/S axis and one E/W axis — that means the
    "matches" were a false positive on ordinary text, not real coords,
    and the caller should fall through to the next pattern / place.
    """
    lat_idx = next((i for i, h in enumerate(hems) if h in ("N", "S")), None)
    lon_idx = next((i for i, h in enumerate(hems) if h in ("E", "W")), None)
    if lat_idx is None or lon_idx is None or lat_idx == lon_idx:
        return None
    return vals[lat_idx], vals[lon_idx]


def check_bounds(lat: float, lon: float, raw: str) -> None:
    if not (LAT_MIN <= lat <= LAT_MAX):
        raise ValueError(f'Latitude {lat} out of range [{LAT_MIN}, {LAT_MAX}] in "{raw}"')
    if not (LON_MIN <= lon <= LON_MAX):
        raise ValueError(f'Longitude {lon} out of range [{LON_MIN}, {LON_MAX}] in "{raw}"')


def classify_location(text: str) -> ParsedLocation:
    """
    Classify raw chat input as coordinates or a place description.

    - Never calls the network, agent, or map layer.
    - Out-of-bounds coordinates raise ValueError immediately; never
      returned as partial coordinates, never fall through to place.
    - Strings that look like a broken coordinate pair (numbers/punctuation
      only, no place-name text) raise ValueError rather than silently
      becoming a place query.
    """
    if text is None:
        raise ValueError("Location text cannot be empty")

    raw = text.strip()
    if not raw:
        raise ValueError("Location text cannot be empty")

    # 1. Labeled decimal: "lat: X lon: Y"
    m = _LABELED_PATTERN.match(raw)
    if m:
        lat, lon = float(m.group("lat")), float(m.group("lon"))
        check_bounds(lat, lon, raw)
        return ParsedLocation(kind="coordinates", raw=raw, lat=lat, lon=lon)

    # 2. DMS: exactly two tokens, each with a hemisphere letter
    dms_matches = list(_DMS_TOKEN_PATTERN.finditer(raw))
    if len(dms_matches) == 2:
        vals = [
            _dms_to_decimal(mm.group("deg"), mm.group("min"), mm.group("sec"), mm.group("hem"))
            for mm in dms_matches
        ]
        hems = [mm.group("hem").upper() for mm in dms_matches]
        ordered = _order_by_hemisphere(vals, hems)
        if ordered:
            lat, lon = ordered
            check_bounds(lat, lon, raw)
            return ParsedLocation(kind="coordinates", raw=raw, lat=lat, lon=lon)

    # 3. Decimal + hemisphere letters: "34.2368 N, 84.4908 W"
    hem_matches = list(_DECIMAL_HEM_PATTERN.finditer(raw))
    if len(hem_matches) == 2:
        vals, hems = [], []
        for mm in hem_matches:
            v = float(mm.group("val"))
            hem = mm.group("hem").upper()
            if hem in ("S", "W"):
                v = -v
            vals.append(v)
            hems.append(hem)
        ordered = _order_by_hemisphere(vals, hems)
        if ordered:
            lat, lon = ordered
            check_bounds(lat, lon, raw)
            return ParsedLocation(kind="coordinates", raw=raw, lat=lat, lon=lon)

    # 4. Plain decimal pair: "34.2368, -84.4908"
    m = _PLAIN_PAIR_PATTERN.match(raw)
    if m:
        lat, lon = float(m.group("lat")), float(m.group("lon"))
        check_bounds(lat, lon, raw)
        return ParsedLocation(kind="coordinates", raw=raw, lat=lat, lon=lon)

    # No coordinate pattern matched. Purely numeric/punctuation strings are
    # a malformed coordinate attempt (single number, 3+ numbers, bad
    # hemisphere combo) — fail loudly instead of geocoding garbage.
    if _LOOKS_NUMERIC_PATTERN.match(raw):
        raise ValueError(
            f'"{raw}" looks like coordinates but could not be parsed. '
            f'Expected "lat, lon" (decimal) or DMS with N/S/E/W.'
        )

    return ParsedLocation(kind="place", raw=raw, place_query=raw)
