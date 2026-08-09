"""LangChain tool: builds FireMapSim simulation config from validated parameters."""

import json

from langchain_core.tools import tool

VALID_CELL_RESOLUTIONS = [2, 3, 5, 10, 15, 30]
VALID_CELL_SPACE_DIMENSIONS = [50, 100, 150, 200]


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
