"""LangChain tool: plain-English FireMapSim UI step instructions."""

import json

from langchain_core.tools import tool

# Keys that name a single on-page control use the same names as
# playwright_guide/highlighting.py's STEP_SELECTORS, so both files describe
# the same controls under the same vocabulary (tests/test_agent_tools.py
# guards this). Every entry is written for the user to perform themselves —
# the agent never operates the page.
_UI_STEPS: dict[str, str] = {
    "set_project_location": (
        "First pan and zoom the map to the area you want to simulate. Then click the "
        "Set Project Location button in the map drawing row — the simulation region is "
        "centered on the current map view."
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
        "and choose 2, 3, 5, 10, 15, or 30 meters per cell (default 30). Smaller cells give "
        "finer detail but cover a smaller area."
    ),
    "cell_dimension": (
        "In the grid settings row, open the Cell Space Dimension dropdown and choose 50, "
        "100, 150, or 200 cells per side (default 50). Combined with Cell Resolution, this "
        "sets how large the simulation area is — for example 30 m × 50 cells is a 1.5 km "
        "square."
    ),
    "simulation_duration": (
        "Find the Simulation Duration box in the config bar (separate from the wind fields). "
        "Type the run length in seconds — typically 6,000 to 30,000; the default 12,000 is "
        "about 3 hours 20 minutes."
    ),
    "wind_speed": (
        "Find the Wind Speed box in the config bar. Type the wind speed in km/h (0–100, "
        "default 10)."
    ),
    "wind_degree": (
        "Find the Wind Degree box next to Wind Speed. Type the direction in degrees — "
        "0 is North, 90 is East, 180 is South, 270 is West."
    ),
    "wind_settings": (
        "Wind is set with two boxes in the config bar: Wind Speed (km/h, 0–100) and Wind "
        "Degree (0 is North, 90 is East, 180 is South, 270 is West)."
    ),
    "get_terrain_fuel": (
        "Click Get Terrain/Fuel Data in the terrain display row. This is optional and "
        "visual only — it loads fuel layers for the current grid area."
    ),
    "show_fuel": (
        "After Get Terrain/Fuel Data has loaded, click Show Fuel in the terrain display row "
        "to see the fuel layer on the map. Visual only — it doesn't change the setup."
    ),
    "show_slope": (
        "After Get Terrain/Fuel Data has loaded, click Show Slope in the terrain display row "
        "to see terrain slope on the map. Visual only — it doesn't change the setup."
    ),
    "show_aspect": (
        "After Get Terrain/Fuel Data has loaded, click Show Aspect in the terrain display row "
        "to see which way slopes face. Visual only — it doesn't change the setup."
    ),
    "start_simulation": (
        "When your project area, ignition, and settings are ready, click Start Simulation Run."
    ),
    "reset_simulation": (
        "Click Reset Simulation to clear the current results so you can change settings and "
        "run again."
    ),
    "show_results": (
        "After the run completes, click Show Simulation Result, adjust Animation Speed, "
        "toggle Show/Hide Fire Layer, and drag the Simulation Time slider to review spread."
    ),
    "load_sample": (
        "Click Load Sample Project in the project file row to open a ready-made example "
        "project you can explore."
    ),
    "save_project": (
        "Click Save Project in the project file row to save your project to your account. "
        "You need to be logged in."
    ),
    "download_project": (
        "Click Download Project in the project file row to save the project as a file on "
        "your computer."
    ),
    "upload_project": (
        "Click Upload Project in the project file row and pick a project file you "
        "previously downloaded."
    ),
    "close_project": (
        "Click Close Project to close the project you're working on."
    ),
}


@tool
def explain_ui_step(step: str) -> str:
    """Return plain-English instructions for a FireMapSim UI step by name.

    Always returns JSON: {"step", "instructions"} on a hit, or
    {"error", "requested_step", "available_steps"} for an unknown step so the
    agent can pick the right one without a second round trip.
    """
    if step in _UI_STEPS:
        return json.dumps({"step": step, "instructions": _UI_STEPS[step]})
    return json.dumps(
        {
            "error": "Unknown step",
            "requested_step": step,
            "available_steps": list(_UI_STEPS.keys()),
        }
    )
