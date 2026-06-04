"""
projection_converter.py

Converts between WGS84 lat/lon and FireMapSim grid cell indices.

FireMapSim coordinate system facts:
  - Projected CRS: EPSG:2239 (NAD83 / Georgia State Plane East, US survey feet)
  - proj_center_lng / proj_center_lat in the project JSON are the projected
    coordinates (in feet) of the grid's center point
  - Grid is always 200x200 cells at 30m resolution (6km x 6km domain)
  - Cell (0,0) is bottom-left; cell (199,199) is top-right
  - Grid indices in segment/supLine definitions are integers [0, 199]

Note on coverage:
  EPSG:2239 is valid for Georgia east of ~84.5°W. For locations further west,
  swap _FIRESIM_CRS to EPSG:2240 (Georgia State Plane West). All other logic
  stays the same.
"""

import math

from geopy.geocoders import Nominatim
from pyproj import Transformer

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_FIRESIM_CRS = "EPSG:2239"  # NAD83 / Georgia State Plane East (US survey feet)
_WGS84_CRS = "EPSG:4326"

_METERS_TO_FEET = 3.28083989501312  # exact US survey foot conversion
CELL_SIZE_FT = 30.0 * _METERS_TO_FEET  # 98.4252 ft per 30m cell
GRID_SIZE = 200  # always 200x200 in FireMapSim

_ACRES_TO_SQM = 4046.856
_CELL_SPACE_DIMENSIONS = [50, 100, 150, 200]
_PREFERRED_CELL_RESOLUTION = 30

_to_firesim = Transformer.from_crs(_WGS84_CRS, _FIRESIM_CRS, always_xy=True)
_to_wgs84 = Transformer.from_crs(_FIRESIM_CRS, _WGS84_CRS, always_xy=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def geocode_location(description: str) -> tuple[float, float]:
    """
    Geocode a plain address or place name to WGS84 center coordinates.

    Args:
        description: Address or place string to geocode.

    Returns:
        (center_lat, center_lon) in decimal degrees (WGS84).

    Raises:
        ValueError: If geocoding returns no result.
    """
    text = description.strip()
    if not text:
        raise ValueError("location description cannot be empty")

    geolocator = Nominatim(user_agent="firesim-ai")
    geo = geolocator.geocode(text)
    if geo is None:
        raise ValueError(
            f'Could not geocode location "{text}". '
            "Try a more specific address or place name."
        )
    return float(geo.latitude), float(geo.longitude)


def acres_to_sim_bounds(center_lat: float, center_lon: float, acres: float) -> dict:
    """
    Derive grid settings that cover a square region of the given acreage.

    Prefers 30 m cell resolution and picks the smallest cellSpaceDimension from
    [50, 100, 150, 200] whose total side length exceeds the computed side length.
    """
    if acres <= 0:
        raise ValueError("acres must be a positive number")

    side_m = math.sqrt(acres * _ACRES_TO_SQM)
    cell_resolution = _PREFERRED_CELL_RESOLUTION
    cell_space_dimension = _CELL_SPACE_DIMENSIONS[-1]
    for dim in _CELL_SPACE_DIMENSIONS:
        if cell_resolution * dim > side_m:
            cell_space_dimension = dim
            break

    return {
        "center_lat": center_lat,
        "center_lon": center_lon,
        "acres": acres,
        "side_m": side_m,
        "cellResolution": cell_resolution,
        "cellSpaceDimension": cell_space_dimension,
    }


def latlon_to_proj_center(lat: float, lon: float) -> tuple[float, float]:
    """
    Convert a WGS84 center point to FireMapSim proj_center_lng / proj_center_lat.

    Use this when the farmer gives a location (address → geocoded lat/lon) and
    you need to set the project area center for a new simulation.

    Args:
        lat: Center latitude in decimal degrees (WGS84)
        lon: Center longitude in decimal degrees (WGS84)

    Returns:
        (proj_center_lng, proj_center_lat) in projected feet (EPSG:2239),
        ready to write directly into the FireMapSim project JSON.
    """
    proj_x, proj_y = _to_firesim.transform(lon, lat)
    return proj_x, proj_y


def latlon_to_grid(
    lat: float,
    lon: float,
    proj_center_lng: float,
    proj_center_lat: float,
) -> tuple[float, float]:
    """
    Convert WGS84 lat/lon to FireMapSim grid cell indices (x, y).

    Args:
        lat: Latitude in decimal degrees (WGS84)
        lon: Longitude in decimal degrees (WGS84)
        proj_center_lng: proj_center_lng from FireMapSim project JSON (feet)
        proj_center_lat: proj_center_lat from FireMapSim project JSON (feet)

    Returns:
        (grid_x, grid_y) as floats. Use latlon_to_grid_int() for JSON segment values.

    Raises:
        ValueError: If the point falls outside the 200x200 grid boundary.
    """
    proj_x, proj_y = _to_firesim.transform(lon, lat)

    half = GRID_SIZE / 2.0
    grid_x = (proj_x - proj_center_lng) / CELL_SIZE_FT + half
    grid_y = (proj_y - proj_center_lat) / CELL_SIZE_FT + half

    # Allow a half-cell tolerance at the edges
    if not (-0.5 <= grid_x <= GRID_SIZE + 0.5 and -0.5 <= grid_y <= GRID_SIZE + 0.5):
        raise ValueError(
            f"({lat:.5f}, {lon:.5f}) maps to grid ({grid_x:.1f}, {grid_y:.1f}), "
            f"which is outside the {GRID_SIZE}x{GRID_SIZE} grid. "
            f"Is the proj_center set correctly for this location?"
        )

    return grid_x, grid_y


def latlon_to_grid_int(
    lat: float,
    lon: float,
    proj_center_lng: float,
    proj_center_lat: float,
) -> tuple[int, int]:
    """
    Same as latlon_to_grid but rounds to the nearest integer cell index.

    Use this to build start_x / end_x / start_y / end_y values in FireMapSim JSON.
    """
    x, y = latlon_to_grid(lat, lon, proj_center_lng, proj_center_lat)
    return round(x), round(y)


def grid_to_latlon(
    grid_x: float,
    grid_y: float,
    proj_center_lng: float,
    proj_center_lat: float,
) -> tuple[float, float]:
    """
    Convert FireMapSim grid cell indices back to WGS84 lat/lon.

    Useful for confirming placement or displaying results to the user.

    Args:
        grid_x: Grid x index (0 to 200)
        grid_y: Grid y index (0 to 200)
        proj_center_lng: proj_center_lng from FireMapSim project JSON (feet)
        proj_center_lat: proj_center_lat from FireMapSim project JSON (feet)

    Returns:
        (lat, lon) in decimal degrees (WGS84)
    """
    half = GRID_SIZE / 2.0
    proj_x = (grid_x - half) * CELL_SIZE_FT + proj_center_lng
    proj_y = (grid_y - half) * CELL_SIZE_FT + proj_center_lat

    lon, lat = _to_wgs84.transform(proj_x, proj_y)
    return lat, lon


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    PCX = -35619.01701560877  # from ignitionPlan.json
    PCY = 1526271.822562622

    print("=== latlon_to_proj_center ===")
    center_lat, center_lon = grid_to_latlon(100, 100, PCX, PCY)
    pcx2, pcy2 = latlon_to_proj_center(center_lat, center_lon)
    assert abs(pcx2 - PCX) < 0.01 and abs(pcy2 - PCY) < 0.01, "proj_center round-trip failed!"
    print(f"  lat={center_lat:.6f}, lon={center_lon:.6f} → pcx={pcx2:.3f}, pcy={pcy2:.3f} ✓")

    print("\n=== grid ↔ latlon round-trips ===")
    test_points = [
        ("Center      (100, 100)", 100, 100),
        ("Corner      (  0,   0)", 0, 0),
        ("Corner      (200, 200)", 200, 200),
        ("Ignition    ( 78, 146)", 78, 146),
        ("Sup line    ( 55, 133)", 55, 133),
    ]
    for label, gx, gy in test_points:
        lat, lon = grid_to_latlon(gx, gy, PCX, PCY)
        gx2, gy2 = latlon_to_grid(lat, lon, PCX, PCY)
        assert abs(gx2 - gx) < 0.01 and abs(gy2 - gy) < 0.01, f"Round-trip failed for {label}"
        print(f"  {label} → ({lat:.6f}, {lon:.6f}) → ({gx2:.1f}, {gy2:.1f}) ✓")

    print("\n=== latlon_to_grid_int ===")
    lat, lon = grid_to_latlon(78, 146, PCX, PCY)
    ix, iy = latlon_to_grid_int(lat, lon, PCX, PCY)
    assert (ix, iy) == (78, 146), f"Expected (78, 146), got ({ix}, {iy})"
    print(f"  ({lat:.6f}, {lon:.6f}) → ({ix}, {iy}) ✓")

    print("\n=== out-of-bounds guard ===")
    try:
        latlon_to_grid(0.0, 0.0, PCX, PCY)
        print("  ERROR: should have raised ValueError")
    except ValueError as e:
        print(f"  Caught correctly: {e}")

    print("\nAll tests passed ✓")
