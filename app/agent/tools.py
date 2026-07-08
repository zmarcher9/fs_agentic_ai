"""LangChain tools for FireMapSim geocoding, config building, and UI guidance."""

import json

from langchain_core.tools import tool

from app.core.projection_converter import acres_to_sim_bounds, geocode_location

VALID_CELL_RESOLUTIONS = [2, 3, 5, 10, 15, 30]
VALID_CELL_SPACE_DIMENSIONS = [50, 100, 150, 200]

_UI_STEPS: dict[str, str] = {
    "apply_config": (
        "In the chat widget (orange circle, bottom right), click Apply on the config the "
        "assistant provided. This applies the settings and centers the map — you can skip "
        "Set Project Location afterward."
    ),
    "set_project_location": (
        "The map has already moved to your project area. Click the Set Project Location "
        "button in the map drawing row to confirm the simulation region."
    ),
    "set_line_ignition": (
        "Click Set Line Ignition in the map drawing row. Left-click on the map to place "
        "points along the path where you want the fire to start. Right-click when done — "
        "the line appears in red."
    ),
    "set_point_ignition": (
        "Click Set Point Ignition in the map drawing row. Left-click once on the map for "
        "a single ignition point. It appears as a red-orange marker."
    ),
    "set_fuel_brake": (
        "Click Set Fuel Brake in the map drawing row. Left-click to draw a path along your "
        "fuel break (fire barrier). Right-click to finish — the line appears in dark blue."
    ),
    "set_dynamic_ignition": (
        "Enable the Dynamic Ignition checkbox first, then click Set Dynamic Ignition. Draw "
        "the ignition path and configure team, speed, and mode options as needed."
    ),
    "cell_resolution": (
        "In the grid settings row at the top of Config, open the Cell Resolution dropdown "
        "and choose your value. Smaller cells give finer detail but cover a smaller area."
    ),
    "cell_space_dimension": (
        "In the grid settings row, open the Cell Space Dimension dropdown and choose your "
        "value. Combined with cell resolution, this sets how large the simulation area is."
    ),
    "simulation_duration": (
        "Find the Simulation Duration box in the config bar (separate from the wind fields). "
        "Enter the run length in seconds."
    ),
    "wind_speed": (
        "Find the Wind Speed box in the config bar. Enter wind speed in km/h (0–100)."
    ),
    "wind_degree": (
        "Find the Wind Degree box next to Wind Speed. Enter direction in degrees — "
        "0 is North, 90 is East, 180 is South, 270 is West."
    ),
    "wind_settings": (
        "In the config bar, use the Wind Speed and Wind Degree boxes. Do not change "
        "Simulation Duration unless the user asked about run length."
    ),
    "get_terrain_fuel": (
        "Click Get Terrain/Fuel Data in the terrain display row. This is optional and "
        "visual only — it loads fuel layers for the current grid area."
    ),
    "start_simulation": (
        "When your project area, ignition, and settings are ready, click Start Simulation Run. "
        "Use Reset Simulation if you need to clear results and run again."
    ),
    "show_results": (
        "After the run completes, click Show Simulation Result, adjust Animation Speed, "
        "toggle Show/Hide Fire Layer, and drag the Simulation Time slider to review spread."
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
    available = ", ".join(_UI_STEPS.keys())
    return f"Step '{step}' not recognised. Available steps are: {available}"


TOOLS = [geocode_and_configure, build_project_config, explain_ui_step]
