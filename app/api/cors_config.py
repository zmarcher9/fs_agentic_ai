"""Compatibility access to the environment-configured CORS allowlist."""

from app.config import get_settings


def get_allowed_origins() -> list[str]:
    return get_settings().cors_origin_list
