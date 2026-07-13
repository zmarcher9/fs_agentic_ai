"""
Shared zoom policy for map navigation.

Imported by app/agent/tools_navigate_map.py, app/browser/pool.py, and
app/api/routes_map.py so all three entry points enforce the identical
rule — same reasoning as location_parser.check_bounds for lat/lon.

Policy: REJECT out-of-range or non-int zoom. Never silently clamp.
Silently substituting a different value than what was requested hides
a bug from whoever asked (agent or HTTP caller) instead of letting them
correct it and retry.
"""

from typing import Optional

MIN_ZOOM = 1
MAX_ZOOM = 22
DEFAULT_ZOOM = 13  # matches PROJECT_ZOOM


def validate_zoom(zoom: Optional[int]) -> int:
    """
    Resolve `zoom` to a concrete, validated int. None -> DEFAULT_ZOOM.
    Raises ValueError on anything out of [MIN_ZOOM, MAX_ZOOM] or non-int.
    """
    resolved = DEFAULT_ZOOM if zoom is None else zoom
    if not isinstance(resolved, int) or isinstance(resolved, bool):
        raise ValueError(f"zoom must be an integer, got {zoom!r}")
    if not (MIN_ZOOM <= resolved <= MAX_ZOOM):
        raise ValueError(f"zoom must be between {MIN_ZOOM} and {MAX_ZOOM}, got {resolved}")
    return resolved
