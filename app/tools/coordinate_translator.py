"""LangChain tool: converts natural language locations to FireMapSim simulation coordinates."""

import json
import math

from geopy.geocoders import Nominatim
from langchain_core.tools import tool
from shapely.geometry import box

_ACRES_TO_SQM = 4046.8564224
_M_PER_DEG_LAT = 111_000.0


def _parse_input(query: str) -> tuple[str, float]:
    text = query.strip()
    loc_prefix = "location:"
    acres_marker = ", acres:"
    lower = text.lower()
    if not lower.startswith(loc_prefix):
        raise ValueError(
            'Input must be in the format: "location: <description>, acres: <number>"'
        )
    marker_idx = lower.find(acres_marker)
    if marker_idx == -1:
        raise ValueError(
            'Input must be in the format: "location: <description>, acres: <number>"'
        )
    location = text[len(loc_prefix) : marker_idx].strip()
    if not location:
        raise ValueError("location description cannot be empty")
    try:
        acres = float(text[marker_idx + len(acres_marker) :].strip())
    except ValueError as exc:
        raise ValueError("acres must be a number") from exc
    if acres <= 0:
        raise ValueError("acres must be a positive number")
    return location, acres


def _acres_to_half_degrees(acres: float, center_lat: float) -> tuple[float, float]:
    """Return half side length in degrees (lat, lon) for a square of the given acreage."""
    side_m = math.sqrt(acres * _ACRES_TO_SQM)
    half_lat_deg = (side_m / 2) / _M_PER_DEG_LAT
    lat_rad = math.radians(center_lat)
    m_per_deg_lon = _M_PER_DEG_LAT * max(math.cos(lat_rad), 1e-6)
    half_lon_deg = (side_m / 2) / m_per_deg_lon
    return half_lat_deg, half_lon_deg


def _bounding_box_corners(
    center_lat: float,
    center_lon: float,
    half_lat_deg: float,
    half_lon_deg: float,
) -> list[list[float]]:
    min_lon = center_lon - half_lon_deg
    max_lon = center_lon + half_lon_deg
    min_lat = center_lat - half_lat_deg
    max_lat = center_lat + half_lat_deg
    polygon = box(min_lon, min_lat, max_lon, max_lat)
    return [[lat, lon] for lon, lat in list(polygon.exterior.coords)[:-1]]


def resolve_location(query: str) -> dict:
    """Geocode a formatted query and compute a bounding box for the requested acreage."""
    location_description, acres = _parse_input(query)
    geolocator = Nominatim(user_agent="firesim-ai")
    geo = geolocator.geocode(location_description)
    if geo is None:
        raise ValueError(
            f'Could not geocode location "{location_description}". '
            "Try a more specific address or place name."
        )
    center_lat = float(geo.latitude)
    center_lon = float(geo.longitude)
    half_lat, half_lon = _acres_to_half_degrees(acres, center_lat)
    return {
        "location_query": query,
        "center_lat": center_lat,
        "center_lon": center_lon,
        "bounding_box": _bounding_box_corners(center_lat, center_lon, half_lat, half_lon),
        "acres": acres,
        "confirmed": False,
    }


@tool("coordinate_translator")
def coordinate_translator(input: str) -> str:
    """Geocode a natural-language location and build a bounding box for a given acreage.

    Accepts a single string in the format:
    "location: <description>, acres: <number>"

    Uses Nominatim to resolve the location to WGS84 coordinates, then computes a
    rectangular bounding polygon centered on that point. The box side length is derived
    from the acreage (assuming a square region).

    Args:
        input: Location description and acreage, e.g. "location: Yosemite Valley, acres: 50"

    Returns:
        JSON string with location_query, center_lat, center_lon, bounding_box
        (four [lat, lon] corners), acres, and confirmed=false.
    """
    return json.dumps(resolve_location(input))
