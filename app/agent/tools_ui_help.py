"""LangChain tool: plain-English FireMapSim UI step instructions."""

import json

from langchain_core.tools import tool

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
def explain_ui_step(step: str) -> str:
    """Return plain-English instructions for a FireMapSim UI step by name."""
    if step in _UI_STEPS:
        return _UI_STEPS[step]
    # Unknown step: was falling through to a plain f-string, which the
    # agent can narrate fine but callers/tests expecting a structured
    # result (same "never silently succeed / never fake a result"
    # pattern as navigate_map and resolve_location) couldn't parse.
    # Return the same shape those tools use: a JSON error the caller
    # can branch on, with the valid options included so the agent can
    # correct the user without a second round trip.
    return json.dumps(
        {
            "error": "Unknown step",
            "requested_step": step,
            "available_steps": list(_UI_STEPS.keys()),
        }
    )
