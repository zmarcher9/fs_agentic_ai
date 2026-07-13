"""
CORS origin allowlist for the FastAPI app.

Replacing allow_origins=["*"] matters specifically because
POST /api/map/navigate drives a real browser session — a wildcard
origin lets any website's JS make requests against a visitor's session
from a different tab, as long as it can obtain/guess a session id.
Locking origins down is one layer; unguessable session tokens (see
app/core/session_tokens.py) are the other — you need both.
"""

ALLOWED_ORIGINS = [
    # TODO: confirm this is the actual FireMapSim deployment origin —
    # I don't have visibility into where it's hosted.
    "https://firesim.cs.gsu.edu",
    "http://localhost:5173",  # local dev (Vite default) — drop for prod deploys
]
