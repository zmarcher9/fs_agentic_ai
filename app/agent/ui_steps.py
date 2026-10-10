"""Plain-English FireMapSim per-control instructions (the agent's step reference).

Content is grounded in the SIMS Lab FireMapSim project report and slides
(Wei Zhao, 2025) and Dr. Hu's usage email. Facts those sources don't state
(e.g. whether Wind Degree is the direction wind comes from or blows toward)
are deliberately left out rather than guessed.
"""

import re

# The agent sees every entry in its (cached) system prompt and returns the
# keys of the controls its answer is about. Keys that name a single on-page
# control use the same names as playwright_guide/highlighting.py's
# STEP_SELECTORS (tests/test_ui_steps.py guards this). Every entry is written
# for the user to perform themselves — the agent never operates the page.
# Each entry opens with its own control's label so the guide's text-based
# fallback (used only with a server that sends no `highlight` list) lands on
# the right control.
UI_STEPS: dict[str, str] = {
    "set_project_location": (
        "Set Project Location is the first button in the button row. First pan and zoom the "
        "map to the area you want to simulate, then click it — the simulation region is "
        "centered on the current map view and outlined on the map. Once a project area is "
        "set, the same button reads Go to Project Location."
    ),
    "go_project_location": (
        "Go to Project Location appears in place of Set Project Location once a project area "
        "is set. Click it to bring the map back to your project area; it also shows the "
        "project's exact latitude/longitude."
    ),
    "selected_area": (
        "Selected Region, next to the grid dropdowns, shows how big the simulation area is "
        "(for example 6000m * 6000m). It is Cell Resolution × Cell Space Dimension and "
        "updates when you change either dropdown."
    ),
    "set_line_ignition": (
        "Set Line Ignition is in the button row. Click it, then left-click on the map to "
        "place points along the path where the fire should start; right-click to finish. "
        "These are static ignition lines, drawn in red: every cell along them is on fire at "
        "the very start of the run."
    ),
    "set_point_ignition": (
        "Set Point Ignition is in the button row. Click it, then left-click on the map for "
        "each single ignition point. To remove a point, select it and confirm the removal."
    ),
    "set_fuel_brake": (
        "Set Fuel Brake is in the button row. Click it, then left-click to draw a path along "
        "your fuel break (a barrier the fire can't cross); right-click to finish. The line "
        "appears in dark blue."
    ),
    "set_dynamic_ignition": (
        "Set Dynamic Ignition only appears after you tick the Dynamic Ignition checkbox at "
        "the top. Click it and draw ignition lines like Set Line Ignition — these show in "
        "orange. Instead of all igniting at once, an ignition team walks each line in order. "
        "Select a line to set its Ignition Team, Ignition Speed, Ignition Mode, and Spot "
        "Distance (m)."
    ),
    "rearrange_ignition": (
        "Route and Rearrange appear on the left of the map in dynamic ignition mode. Route "
        "plays an animation of the path the ignition teams will walk. Rearrange lists every "
        "ignition line with its order and team: drag lines to change the order, click "
        "Reverse on a line to flip its direction, then click Rearrange Done."
    ),
    "delete_line": (
        "Delete appears on the left of the map when you select a line. Enter the matching "
        "mode first — Set Line Ignition or Set Dynamic Ignition for ignition lines, Set Fuel "
        "Brake for fuel breaks — click the line, then click Delete. You can draw new lines "
        "any time."
    ),
    "mark_burned": (
        "Mark Inner Cells as Burned/Unburned marks an area as already burned before the run "
        "starts. Draw a closed loop with Set Line Ignition (static lines, not dynamic), select "
        "one of its lines, then click the Mark Inner Cells as Burned/Unburned button on the "
        "left; click again to undo. You can also select cells in Show Cell Info mode and use "
        "Mark as Burned / Mark as Unburned in the popup."
    ),
    "cell_resolution": (
        "Cell Resolution is a dropdown at the top of the page. Choose 2, 3, 5, 10, 15, or 30 "
        "meters per cell (default 30). Smaller cells give finer detail but cover a smaller "
        "area."
    ),
    "cell_dimension": (
        "Cell Space Dimension is the dropdown next to Cell Resolution. Choose 50, 100, 150, "
        "or 200 cells per side. Together with Cell Resolution it sets the size of the "
        "simulation area — for example 30 m × 200 cells is a 6,000 m square, shown in the "
        "Selected Region readout."
    ),
    "show_grid_layer": (
        "Show Grid Layer is a checkbox at the top. Tick it to draw the simulation grid over "
        "the map so you can see each cell; untick it to hide the grid."
    ),
    "simulation_duration": (
        "Simulation Duration (s) is a number box in the settings row. Type the run length in "
        "seconds — typically 6,000 to 30,000; 12,000 is about 3 hours 20 minutes."
    ),
    "wind_speed": (
        "Wind Speed is the number box after Simulation Duration. Type the wind speed (km/h, "
        "0–100, default 10)."
    ),
    "wind_degree": (
        "Wind Degree is the number box next to Wind Speed. Type the direction in degrees on "
        "the compass — 0 is North, 90 is East, 180 is South, 270 is West."
    ),
    "wind_settings": (
        "Wind is set with two number boxes in the settings row: Wind Speed (km/h, 0–100) and "
        "Wind Degree (compass degrees: 0 North, 90 East, 180 South, 270 West)."
    ),
    "map_style": (
        "Select Map Style is the dropdown in the top-left corner of the map. Pick terrain, "
        "satellite, or street. Satellite helps you trace ignition lines along dirt roads and "
        "trails that the terrain map doesn't show."
    ),
    "get_terrain_fuel": (
        "Get Terrain/Fuel Data is the first button in the second row. Click it after setting "
        "your project location to load the fuel, slope, and aspect data for every cell. It's "
        "needed before Show Fuel, Show Slope, Show Aspect, or editing cells."
    ),
    "show_fuel": (
        "Show Fuel is in the second row; it works once Get Terrain/Fuel Data has loaded. "
        "Click it to color each cell by fuel type; it then reads Hide Fuel. Only one of fuel, "
        "slope, or aspect shows at a time. Viewing it doesn't change the setup."
    ),
    "show_slope": (
        "Show Slope is in the second row; it works once Get Terrain/Fuel Data has loaded. "
        "Click it to color cells by steepness (0–90 degrees; deeper red is steeper). Viewing "
        "it doesn't change the setup."
    ),
    "show_aspect": (
        "Show Aspect is in the second row; it works once Get Terrain/Fuel Data has loaded. "
        "Click it to color cells by which compass direction the slope faces (gray is flat). "
        "Viewing it doesn't change the setup."
    ),
    "show_cell_info": (
        "Show Cell Info is in the second row (newer versions may call it Edit Cell Data). "
        "Click it, then click a cell to see its fuel type, slope, aspect, and grid "
        "coordinate. Select several cells by clicking more of them or dragging (Shift + drag "
        "selects a rectangle). The popup has Customize Fuel Data, Clear Selection, Mark as "
        "Burned, and Mark as Unburned."
    ),
    "customize_fuel": (
        "Customize Fuel Data is in the Show Cell Info popup. Select the cells, click it, type "
        "the new fuel type number, and click Submit; Restore puts the original data back. "
        "Customize filtered fuel changes only cells of one fuel type within your selection. "
        "You can also enter a fuel reduction level from 0 to 1 — higher slows the fire more; "
        "reduced cells look whitish in Show Fuel. After an edit the Customized Fuel checkbox "
        "is ticked so the run uses your changes; untick it to compare against the original "
        "data."
    ),
    "start_simulation": (
        "Start Simulation Run is in the settings row. Click it when your project area, "
        "ignition, and settings are ready. When the results come back it reads Simulation "
        "Results Received and Show Simulation Result turns green."
    ),
    "show_results": (
        "Show Simulation Result is in the bottom row; it turns green once results are back. "
        "Click it to play the fire spread animation (it then reads Replay Simulation Result). "
        "Use ► to pause or resume, drag the time slider to jump to any moment, raise "
        "Animation Speed to play faster, and Hide Fire Layer to hide the burned area."
    ),
    "record_video": (
        "Record Simulation Video is a checkbox at the top. Tick it before playing the result "
        "to save the animation as a video on your computer."
    ),
    "reset_simulation": (
        "Reset Simulation clears the results but keeps your setup — location, lines, and "
        "settings — so you can change something and run again."
    ),
    "close_project": (
        "Close Project clears everything, results and setup, and starts over. Download or "
        "save the project first if you want to keep it."
    ),
    "load_sample": (
        "Load Sample Project is in the button row. Click it to open a ready-made example "
        "project you can explore and run."
    ),
    "save_project": (
        "Save Project is in the button row. Click it to save the project to your account; you "
        "need to be logged in. Logged-in users can also set a home location the map opens to."
    ),
    "download_project": (
        "Download Project is in the button row. Click it to save the whole project — ignition "
        "lines, settings, and fuel edits — as a .json file on your computer. It also offers "
        "fuel data downloads."
    ),
    "upload_project": (
        "Upload Project is in the button row. Click it and pick a project .json file you "
        "downloaded earlier (or one someone sent you); everything is restored, then click "
        "Start Simulation Run."
    ),
    "user_defined_simulation": (
        "User-defined Simulation is in the top navigation bar. It opens a blank workspace "
        "where you supply your own fuel, slope, and aspect: upload a file for each, or type "
        "one value for the whole area and click Set Fuel, Set Slope, or Set Aspect. "
        "Everything else — ignition lines, running, playback — works the same."
    ),
}

# Visible labels and common phrasings → step key. Lets the model pass what
# it sees on the page ("Wind Degree") in its highlight list.
ALIASES: dict[str, str] = {
    "go_to_location": "go_project_location",
    "go_to_project_location": "go_project_location",
    "selected_region": "selected_area",
    "line_ignition": "set_line_ignition",
    "point_ignition": "set_point_ignition",
    "fuel_brake": "set_fuel_brake",
    "fuel_break": "set_fuel_brake",
    "set_fuel_break": "set_fuel_brake",
    "dynamic_ignition": "set_dynamic_ignition",
    "route": "rearrange_ignition",
    "rearrange": "rearrange_ignition",
    "delete": "delete_line",
    "mark_as_burned": "mark_burned",
    "mark_inner_cells_as_burned_unburned": "mark_burned",
    "cell_space_dimension": "cell_dimension",
    "grid_layer": "show_grid_layer",
    "duration": "simulation_duration",
    "simulation_duration_s": "simulation_duration",
    "wind_direction": "wind_degree",
    "wind": "wind_settings",
    "select_map_style": "map_style",
    "get_terrain_fuel_data": "get_terrain_fuel",
    "hide_fuel": "show_fuel",
    "edit_cell_data": "show_cell_info",
    "customize_fuel_data": "customize_fuel",
    "fuel_reduction": "customize_fuel",
    "start_simulation_run": "start_simulation",
    "show_simulation_result": "show_results",
    "replay_simulation_result": "show_results",
    "animation_speed": "show_results",
    "hide_fire_layer": "show_results",
    "record_simulation_video": "record_video",
    "load_sample_project": "load_sample",
}


def _normalize(step: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", step.lower()).strip("_")


def resolve_step(step: str) -> str | None:
    """Map a key, visible label, or alias to a UI_STEPS key (None if unknown)."""
    key = _normalize(step)
    if key in UI_STEPS:
        return key
    return ALIASES.get(key)
