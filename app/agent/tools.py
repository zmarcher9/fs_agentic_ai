"""LangChain tools for FireMapSim geocoding, config building, and UI guidance."""

import json

from langchain_core.tools import tool

from app.core.projection_converter import acres_to_sim_bounds, geocode_location

VALID_CELL_RESOLUTIONS = [2, 3, 5, 10, 15, 30]
VALID_CELL_SPACE_DIMENSIONS = [50, 100, 150, 200]

_UI_STEPS: dict[str, str] = {
    "apply_config": (
        "In the chat widget (orange circle, bottom right), find the JSON config the assistant "
        "provided and click the Apply button. This instantly applies the settings and centers "
        "the map on your project location — you can skip Set Project Location afterward."
    ),
    "set_project_location": (
        "Click Set Project Location in Cluster 1. This centers the simulation region on the "
        "current map view. Pan and zoom the map to your burn area first, then click the button."
    ),
    "set_line_ignition": (
        "Click Set Line Ignition in Cluster 1. Left-click on the map to place nodes along the "
        "path where you want the fire to start. Right-click when you are done — the line appears "
        "in red."
    ),
    "set_point_ignition": (
        "Click Set Point Ignition in Cluster 1. Left-click once on the map for a single ignition "
        "point. It appears as a red-orange marker."
    ),
    "set_fuel_brake": (
        "Click Set Fuel Brake in Cluster 1. Left-click nodes to draw a path along your fuel break "
        "(fire barrier). Right-click to finish — the line appears in dark blue and fire cannot "
        "cross it."
    ),
    "set_dynamic_ignition": (
        "Enable the Dynamic Ignition checkbox first, then click Set Dynamic Ignition in Cluster 1. "
        "Draw the ignition path and configure team, speed, and mode options as needed."
    ),
    "cell_resolution": (
        "In the Config section second row, open the Cell Resolution dropdown and choose 2, 3, 5, "
        "10, 15, or 30 meters per cell. Smaller values give finer detail but cover a smaller area."
    ),
    "cell_space_dimension": (
        "In the Config section second row, open the Cell Space Dimension dropdown and choose 50, "
        "100, 150, or 200 cells per side. Combined with cell resolution, this sets how large the "
        "simulation area is."
    ),
    "wind_settings": (
        "In Cluster 5, enter Simulation Duration (seconds), Wind Speed (km/h, 0–100), and Wind "
        "Degree (0–360, where 0 is North and 90 is East)."
    ),
    "start_simulation": (
        "When your project area, ignition, and settings are ready, click Start Simulation Run in "
        "Cluster 6. Use Reset Simulation if you need to clear results and run again."
    ),
    "show_results": (
        "After a run completes, use Cluster 7: Show Simulation Result, adjust Animation Speed, "
        "toggle Show/Hide Fire Layer, and scrub the Simulation Time slider to review spread over "
        "time."
    ),
}


@tool
def geocode_and_configure(location: str, acres: float) -> str:
    """Geocode a place name and compute recommended FireMapSim grid settings for the given acreage."""
    lat, lon = geocode_location(location)
    result = acres_to_sim_bounds(lat, lon, acres)
    return json.dumps(result)


@tool
def build_project_config(
    center_lat: float,
    center_lon: float,
    cell_resolution: int,
    cell_space_dimension: int,
    wind_speed: int,
    wind_degree: int,
    total_sim_time: int,
) -> str:
    """Validate parameters and return a FireMapSim-ready JSON config object."""
    if cell_resolution not in VALID_CELL_RESOLUTIONS:
        raise ValueError(f"cell_resolution must be one of {VALID_CELL_RESOLUTIONS}")
    if cell_space_dimension not in VALID_CELL_SPACE_DIMENSIONS:
        raise ValueError(f"cell_space_dimension must be one of {VALID_CELL_SPACE_DIMENSIONS}")
    if not 0 <= wind_speed <= 100:
        raise ValueError("wind_speed must be between 0 and 100")
    if not 0 <= wind_degree <= 360:
        raise ValueError("wind_degree must be between 0 and 360")
    if not 6000 <= total_sim_time <= 30000:
        raise ValueError("total_sim_time must be between 6000 and 30000 seconds")
    return json.dumps({
        "proj_center_lat": center_lat,
        "proj_center_lng": center_lon,
        "cellResolution": cell_resolution,
        "cellSpaceDimension": cell_space_dimension,
        "windSpeed": wind_speed,
        "windDegree": wind_degree,
        "total_sim_time": total_sim_time,
    })


@tool
def explain_ui_step(step: str) -> str:
    """Return plain-English instructions for a FireMapSim UI step by name."""
    if step in _UI_STEPS:
        return _UI_STEPS[step]
    return json.dumps({"error": "Unknown step", "available_steps": list(_UI_STEPS.keys())})


TOOLS = [geocode_and_configure, build_project_config, explain_ui_step]
