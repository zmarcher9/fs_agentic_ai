"""
Structured audit logging for map-navigation attempts.

One JSON line per navigate call (success or failure), emitted through
the standard `logging` module under the "firesim.audit" logger name so
it composes with whatever handlers/aggregation you already run — this
module only defines the record shape and a convenience emit function.

Used for anomaly detection: rapid pan storms, out-of-pattern coords,
repeated auth/rate-limit failures, one session hammering the same
place, etc.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

logger = logging.getLogger("firesim.audit")

# Default to stdout if the host app hasn't attached its own handler.
# Safe to leave even with a real handler configured elsewhere.
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)

MAX_LABEL_LOG_LENGTH = 200
MAX_ERROR_LOG_LENGTH = 500


def log_navigation(
    session_id: str,
    lat: Optional[float],
    lon: Optional[float],
    zoom: Optional[int],
    label: Optional[str],
    ok: bool,
    source: str,
    error: Optional[str] = None,
) -> None:
    """
    Emit one structured audit record for a navigate attempt.

    `label` is the closest available proxy for "what did the user ask
    for" — navigate_map only ever sees resolved lat/lon/label, not the
    original chat text. Threading the actual raw user message into this
    log would mean passing it from wherever /chat or the agent graph
    first sees it, down through resolve_location and navigate_map —
    not done here since I don't have visibility into that call site.
    """
    record = {
        "timestamp": time.time(),
        "session_id": session_id,
        "requested_location": (label or "")[:MAX_LABEL_LOG_LENGTH] or None,
        "lat": lat,
        "lon": lon,
        "zoom": zoom,
        "ok": ok,
        "source": source,  # "tool" | "http"
        "error": (error or "")[:MAX_ERROR_LOG_LENGTH] or None,
    }
    logger.info(json.dumps(record))
