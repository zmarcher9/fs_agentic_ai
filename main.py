"""Compatibility launcher for the canonical ``api.main:app`` application."""

from api.main import app
from app.config import get_settings


def main() -> None:
    """Run the single canonical ASGI application with one worker."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.app_env == "development",
        workers=1,
    )


if __name__ == "__main__":
    main()
