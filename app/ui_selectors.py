"""
Where each FireMapSim control lives on the page, keyed like UI_STEPS.

Pure data, shared by the live guide (playwright_guide/highlighting.py) and
the embeddable widget the API serves (widget/firesim-helper.js), so neither
copy can drift. Selectors are Playwright selectors: CSS plus `>> nth=N` and
`:has-text('...')`. The widget resolves exactly that subset itself — keep to
it, or teach the widget's resolve() the new syntax.
"""

STEP_SELECTORS: dict[str, str] = {
    "cell_resolution":      "select#cellResolution",
    "cell_dimension":       "select#cellSpaceDimension",
    "selected_area":        "span#selectedSquareArea",
    "set_project_location": "label[for='sPL']",
    "go_project_location":  "label[for='gPL']",
    "set_line_ignition":    "label[for='btnradio1']",
    "set_point_ignition":   "label[for='btnradio1-1']",
    "set_fuel_brake":       "label[for='btnradio2']",
    "get_terrain_fuel":     "label[for='getFuel']",
    "show_fuel":            "label[for='drawFuel']",
    "show_slope":           "label[for='drawSlope']",
    "show_aspect":          "label[for='drawAspect']",
    # The three settings boxes in page order (Duration, Wind Speed, Wind
    # Degree). `nth=` counts matches across the whole page; CSS
    # :nth-of-type counted siblings and broke when each box has its own
    # wrapper. Not yet checked against the live DOM.
    "simulation_duration":  "input.form-control[type='number'] >> nth=0",
    "wind_speed":           "input.form-control[type='number'] >> nth=1",
    "wind_degree":          "input.form-control[type='number'] >> nth=2",
    "start_simulation":     "label[for='startRun']",
    "reset_simulation":     "label[for='btnradio10']",
    "close_project":        "button:has-text('Close Project')",
    "load_sample":          "label[for='loadSample']",
    "save_project":         "label[for='saveProject']",
    "download_project":     "label[for='downloadProject']",
    "upload_project":       "label[for='uploadProject']",
}
